const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');

const REPO_ROOT = path.join(__dirname, '..');
const DOCS_INDEX = path.join(REPO_ROOT, 'docs-index', 'documents.json');
const RECIPES_FILE = path.join(REPO_ROOT, 'tools', 'recipes', 'recipes.json');
const APPLY_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'apply_recipe.py');
const INDEX_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'index_docs.py');
const PLC_EXPORT_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_plc_export.py');
const IO_BANKS_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_io_banks.py');
const AUTOGEN_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_autogen.py');
const WORKBOOK_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_workbook.py');
const IGNITION_BUILD_SCRIPT = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_ignition_build.py');
const IGNITION_DEPLOY_SAFE = path.join(REPO_ROOT, 'tools', 'scripts', '_deploy_designer_safe_ignition.py');
const DEFAULT_AUTOGEN_LIBRARY = path.join(REPO_ROOT, 'tools', 'libraries', 'OReilly_Library_v3.L5X');
const ACTIVE_META = path.join(REPO_ROOT, 'workspace', 'active-meta.json');
const ACTIVE_DIR = path.join(REPO_ROOT, 'workspace', 'active');
const PRINTS_DIR = path.join(REPO_ROOT, 'workspace', 'prints');
const AUTOGEN_WORKBOOK_PATH = path.join(REPO_ROOT, 'workspace', 'active', 'autogen_workbook.json');

function configureElectronStorage() {
  // Keep Chromium caches off OneDrive / worktree — Local AppData only.
  // backend_impl "Critical error -8" / "Failed to save user data" = corrupt or locked
  // Chromium profile. Fix: close all instances, delete %LOCALAPPDATA%\FortnaPlusDashboard.
  const root = path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    'FortnaPlusDashboard'
  );
  const diskCache = path.join(root, 'disk-cache');
  const gpuCache = path.join(root, 'gpu-cache');
  for (const dir of [root, diskCache, gpuCache]) {
    try { fs.mkdirSync(dir, { recursive: true }); } catch (_) { /* ignore */ }
  }
  try {
    app.setPath('userData', root);
    app.setPath('sessionData', path.join(root, 'session'));
  } catch (_) { /* ignore */ }
  app.commandLine.appendSwitch('disk-cache-dir', diskCache);
  app.commandLine.appendSwitch('gpu-cache-dir', gpuCache);
  app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');
  // Tiny HTTP cache — less chance of corrupt multi-GB cache indexes under IT lockdown
  app.commandLine.appendSwitch('disk-cache-size', '1048576');
  // Stability after laptop power cycles / flaky GPU (exit_code=34 spam).
  // Prefer software GL path so Chromium keeps running when the GPU process dies.
  app.commandLine.appendSwitch('disable-gpu');
}

configureElectronStorage();

// Only one FortnaPlus window — second launch focuses the first (avoids cache lock spam)
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const wins = BrowserWindow.getAllWindows();
    if (wins.length) {
      const w = wins[0];
      if (w.isMinimized()) w.restore();
      w.focus();
    }
  });
}

function findPython() {
  for (const cmd of ['py', 'python', 'python3']) {
    const r = spawnSync(cmd, ['--version'], { encoding: 'utf-8', windowsHide: true });
    if (r.status === 0 || /Python/.test(r.stdout || r.stderr || '')) return cmd;
  }
  return null;
}

const PYTHON = findPython();

const PYTHON_MAX_OUT = 64 * 1024 * 1024; // 64MB — large sites (900+ drives)

/** Latest OCR progress payload (for UI polling + event stream). */
let lastOcrProgress = null;

/**
 * Async Python runner — keeps Electron main process responsive.
 * spawnSync was freezing the whole app during OCR (Windows "Not Responding" → kill).
 *
 * options:
 *   env: extra env vars
 *   onProgress: (obj) => void  — FORTNA_PROGRESS lines from stderr
 *   progressEvent: string      — webContents event name (default none)
 *   win: BrowserWindow         — target for progressEvent
 */
function runPythonAsync(args, cwd = REPO_ROOT, options = {}) {
  return new Promise((resolve) => {
    if (!PYTHON) {
      resolve({ ok: false, error: 'Python not found. Install from https://python.org/' });
      return;
    }
    let stdout = '';
    let stderr = '';
    let oversized = false;
    let settled = false;
    let stderrBuf = '';
    const finish = (result) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    let child;
    try {
      child = spawn(PYTHON, args, {
        cwd,
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
          ...(options.env || {}),
        },
      });
    } catch (e) {
      finish({ ok: false, error: e.message || String(e) });
      return;
    }

    const handleProgressLine = (line) => {
      const m = line.match(/^FORTNA_PROGRESS\s+(\{.*\})\s*$/);
      if (!m) return;
      try {
        const payload = JSON.parse(m[1]);
        lastOcrProgress = payload;
        if (typeof options.onProgress === 'function') options.onProgress(payload);
        if (options.progressEvent && options.win && !options.win.isDestroyed()) {
          options.win.webContents.send(options.progressEvent, payload);
        }
      } catch (_) { /* ignore bad progress JSON */ }
    };

    child.stdout.setEncoding('utf-8');
    child.stderr.setEncoding('utf-8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
      if (stdout.length > PYTHON_MAX_OUT) {
        oversized = true;
        try { child.kill(); } catch (_) { /* ignore */ }
      }
    });
    child.stderr.on('data', (chunk) => {
      stderrBuf += chunk;
      // Stream progress lines without retaining multi-MB stderr forever
      let nl;
      while ((nl = stderrBuf.indexOf('\n')) >= 0) {
        const line = stderrBuf.slice(0, nl).replace(/\r$/, '');
        stderrBuf = stderrBuf.slice(nl + 1);
        if (line.startsWith('FORTNA_PROGRESS ')) {
          handleProgressLine(line);
        } else {
          stderr += line + '\n';
          if (stderr.length > PYTHON_MAX_OUT) {
            oversized = true;
            try { child.kill(); } catch (_) { /* ignore */ }
          }
        }
      }
    });
    child.on('error', (err) => {
      finish({ ok: false, error: err.message || String(err) });
    });
    child.on('close', (code, signal) => {
      if (stderrBuf.trim()) {
        const line = stderrBuf.replace(/\r$/, '');
        if (line.startsWith('FORTNA_PROGRESS ')) handleProgressLine(line);
        else stderr += line;
        stderrBuf = '';
      }
      if (oversized) {
        finish({ ok: false, error: 'Python output exceeded 64MB limit' });
        return;
      }
      if (code !== 0) {
        const err = (stderr || stdout || '').trim()
          || (signal ? `killed by ${signal}` : `exit ${code}`);
        finish({ ok: false, error: err, stdout: (stdout || '').trim(), stderr: (stderr || '').trim() });
        return;
      }
      finish({ ok: true, stdout: (stdout || '').trim(), stderr: (stderr || '').trim() });
    });
  });
}

/** Short jobs only (e.g. --version). Prefer runPythonAsync for anything that can take >1s. */
function runPython(args, cwd = REPO_ROOT) {
  if (!PYTHON) {
    return { ok: false, error: 'Python not found. Install from https://python.org/' };
  }
  const r = spawnSync(PYTHON, args, {
    cwd,
    encoding: 'utf-8',
    windowsHide: true,
    maxBuffer: PYTHON_MAX_OUT,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  if (r.status !== 0) {
    const err = (r.stderr || r.stdout || '').trim() || `exit ${r.status}`;
    return { ok: false, error: err };
  }
  return { ok: true, stdout: (r.stdout || '').trim() };
}

function readJson(filePath, fallback = null) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch (e) {
    return fallback;
  }
}

function tokenize(q) {
  return (q || '')
    .toLowerCase()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function scoreDoc(doc, tokens) {
  if (!tokens.length) return 0;
  const hay = [
    doc.title,
    doc.file,
    doc.category,
    doc.summary,
    ...(doc.tasks || []),
  ].join(' ').toLowerCase();
  let score = 0;
  for (const t of tokens) {
    if (doc.title.toLowerCase().includes(t)) score += 8;
    if ((doc.tasks || []).some((x) => x.includes(t))) score += 6;
    if (doc.category.toLowerCase().includes(t)) score += 4;
    if (doc.file.toLowerCase().includes(t)) score += 3;
    if (hay.includes(t)) score += 1;
  }
  return score;
}

function searchDocuments(query, limit = 40) {
  const index = readJson(DOCS_INDEX, { documents: [] });
  const tokens = tokenize(query);
  if (!tokens.length) {
    return { query, count: 0, results: [] };
  }
  const results = (index.documents || [])
    .map((doc) => ({ ...doc, score: scoreDoc(doc, tokens) }))
    .filter((d) => d.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ score, ...doc }) => ({ ...doc, relevance: score }));
  return { query, count: results.length, results };
}

function resolveDocPath(relPath) {
  if (!relPath) return null;
  const safe = relPath.replace(/\.\./g, '');
  const full = path.join(REPO_ROOT, 'docs', 'training', safe);
  return fs.existsSync(full) ? full : null;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#0a0f14',
    title: 'FortnaPlus Control',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false,
    },
    show: false,
    frame: false,
    autoHideMenuBar: true,
  });

  win.loadFile(path.join(REPO_ROOT, 'dashboard', 'index.html'));
  Menu.setApplicationMenu(null);

  win.once('ready-to-show', () => win.show());

  ipcMain.on('window-minimize', () => win.minimize());
  ipcMain.on('window-maximize', () => {
    if (win.isMaximized()) win.unmaximize();
    else win.maximize();
  });
  ipcMain.on('window-close', () => win.close());

  ipcMain.handle('search-docs', async (_event, query) => {
    try {
      return { success: true, ...searchDocuments(query) };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('get-doc-index', async () => {
    const index = readJson(DOCS_INDEX, { documents: [], count: 0 });
    return {
      success: true,
      generated: index.generated || null,
      count: index.count || (index.documents || []).length,
      categories: [...new Set((index.documents || []).map((d) => d.category))].sort(),
    };
  });

  ipcMain.handle('reindex-docs', async () => {
    const r = runPython([INDEX_SCRIPT]);
    if (!r.ok) return { success: false, message: r.error };
    const index = readJson(DOCS_INDEX, { count: 0 });
    return { success: true, count: index.count || 0, generated: index.generated };
  });

  ipcMain.handle('get-recipes', async () => {
    const data = readJson(RECIPES_FILE, { recipes: [] });
    return { success: true, recipes: data.recipes || [] };
  });

  ipcMain.handle('select-archive', async (_event, data) => {
    const multi = !!(data && data.multi);
    const result = await dialog.showOpenDialog(win, {
      title: multi ? 'Select Fortna RUN packages (multi-select)' : 'Select Fortna RUN package',
      filters: [
        { name: 'RUN Archives', extensions: ['tar', 'gz', 'tgz', 'zip'] },
        { name: 'All Files', extensions: ['*'] },
      ],
      properties: multi ? ['openFile', 'multiSelections'] : ['openFile'],
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, canceled: true, paths: [] };
    }
    return {
      success: true,
      path: result.filePaths[0],
      paths: result.filePaths,
    };
  });

  ipcMain.handle('import-run', async (_event, archivePath) => {
    try {
      if (!archivePath || !fs.existsSync(archivePath)) {
        return { success: false, message: 'Archive not found.' };
      }
      const r = await runPythonAsync([APPLY_SCRIPT, 'import', archivePath]);
      if (!r.ok) return { success: false, message: r.error };
      const meta = JSON.parse(r.stdout);
      return { success: true, meta };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  function isWorkspaceLive(meta) {
    if (!meta || !meta.run_dir) return false;
    try {
      const cfg = path.join(meta.run_dir, 'project.cfg');
      return fs.existsSync(cfg);
    } catch (_) {
      return false;
    }
  }

  function clearWorkspaceFiles() {
    // OneDrive-safe: clear contents of active/, remove meta (do not require deleting reparse root)
    const clearDir = (dir) => {
      if (!fs.existsSync(dir)) return;
      for (const name of fs.readdirSync(dir)) {
        const p = path.join(dir, name);
        try {
          fs.rmSync(p, { recursive: true, force: true });
        } catch (_) {
          try {
            if (fs.statSync(p).isDirectory()) {
              for (const child of fs.readdirSync(p)) {
                try { fs.rmSync(path.join(p, child), { recursive: true, force: true }); } catch (__) { /* ignore */ }
              }
            } else {
              fs.unlinkSync(p);
            }
          } catch (__) { /* ignore */ }
        }
      }
    };
    clearDir(ACTIVE_DIR);
    clearDir(path.join(REPO_ROOT, 'workspace', 'active_work'));
    try {
      if (fs.existsSync(ACTIVE_META)) fs.unlinkSync(ACTIVE_META);
    } catch (_) { /* ignore */ }
  }

  ipcMain.handle('get-workspace', async () => {
    let meta = readJson(ACTIVE_META, null);
    // Stale pill fix: if user deleted RUN files but meta remains, treat as empty
    if (meta && !isWorkspaceLive(meta)) {
      try { if (fs.existsSync(ACTIVE_META)) fs.unlinkSync(ACTIVE_META); } catch (_) { /* ignore */ }
      meta = null;
    }
    return {
      success: true,
      active: meta,
      inbox: fs.existsSync(path.join(REPO_ROOT, 'workspace', 'inbox'))
        ? fs.readdirSync(path.join(REPO_ROOT, 'workspace', 'inbox'))
        : [],
      exports: fs.existsSync(path.join(REPO_ROOT, 'exports'))
        ? fs.readdirSync(path.join(REPO_ROOT, 'exports')).filter((f) => f.endsWith('.tar.gz'))
        : [],
    };
  });

  ipcMain.handle('clear-workspace', async () => {
    try {
      clearWorkspaceFiles();
      return { success: true, message: 'Workspace cleared — no RUN loaded.' };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('get-io-banks', async () => {
    try {
      const r = await runPythonAsync([IO_BANKS_SCRIPT, 'banks']);
      if (!r.ok) {
        // Python may print JSON error on stdout or stderr
        try {
          const parsed = JSON.parse(r.error || r.stdout || '{}');
          if (parsed && parsed.error) return { success: false, message: parsed.error };
        } catch (_) { /* ignore */ }
        // Don't dump multi-MB stdout into the UI message
        let msg = r.error || 'Failed to load I/O banks';
        if (typeof msg === 'string' && msg.length > 400) {
          msg = 'Failed to load I/O banks (output too large or Python error). Try refresh again.';
        }
        return { success: false, message: msg };
      }
      const data = JSON.parse(r.stdout);
      if (!data.ok) return { success: false, message: data.error || 'Failed to load I/O banks' };
      return { success: true, ...data };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('ocr-prints', async (_event, data) => {
    try {
      // Preferred: multi-panel sets [{ name, role, paths }]
      let sets = data?.sets || [];
      if (!sets.length && data?.paths?.length) {
        sets = [{
          name: data.panel || 'Unassigned',
          role: data.role || 'remote',
          paths: data.paths,
        }];
      }
      if (!sets.length) return { success: false, message: 'No print files selected.' };

      const tmpDir = path.join(os.tmpdir(), 'fortnaplus-prints');
      fs.mkdirSync(tmpDir, { recursive: true });
      const stamp = Date.now();
      const tmpJson = path.join(tmpDir, `sets-${stamp}.json`);
      const progressFile = path.join(tmpDir, `progress-${stamp}.json`);
      fs.writeFileSync(tmpJson, JSON.stringify({ sets }, null, 2), 'utf-8');
      lastOcrProgress = {
        phase: 'starting',
        pct: 0,
        message: 'Starting OCR…',
        pages_done: 0,
        pages_total: 0,
      };
      if (win && !win.isDestroyed()) {
        win.webContents.send('ocr-progress', lastOcrProgress);
      }

      // Async spawn — OCR can take a while; progress streams via FORTNA_PROGRESS
      const args = [IO_BANKS_SCRIPT, 'ocr-prints', '--sets-json', tmpJson];
      const r = await runPythonAsync(args, REPO_ROOT, {
        env: {
          FORTNA_OCR_PROGRESS: progressFile,
          // Use free cores; override with FORTNA_OCR_WORKERS if needed
        },
        progressEvent: 'ocr-progress',
        win,
      });
      try { fs.unlinkSync(tmpJson); } catch (_) { /* ignore */ }
      try { fs.unlinkSync(progressFile); } catch (_) { /* ignore */ }

      if (!r.ok) {
        try {
          const parsed = JSON.parse(r.error || r.stdout || '{}');
          if (parsed.error) return { success: false, message: parsed.error };
        } catch (_) { /* ignore */ }
        let msg = r.error || 'OCR failed';
        if (typeof msg === 'string' && msg.length > 400) {
          msg = 'OCR failed (see Python/Tesseract logs). Window should stay responsive after relaunch.';
        }
        lastOcrProgress = { phase: 'error', pct: 0, message: msg };
        if (win && !win.isDestroyed()) win.webContents.send('ocr-progress', lastOcrProgress);
        return { success: false, message: msg };
      }
      const result = JSON.parse(r.stdout);
      if (!result.ok) {
        lastOcrProgress = { phase: 'error', pct: 0, message: result.error || 'OCR failed' };
        if (win && !win.isDestroyed()) win.webContents.send('ocr-progress', lastOcrProgress);
        return { success: false, message: result.error || 'OCR failed' };
      }
      lastOcrProgress = {
        phase: 'done',
        pct: 100,
        message: 'OCR complete',
        pages_done: result.ocr_pages_total || 0,
        pages_total: result.ocr_pages_total || 0,
      };
      if (win && !win.isDestroyed()) win.webContents.send('ocr-progress', lastOcrProgress);
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('get-ocr-progress', async () => {
    return { success: true, progress: lastOcrProgress };
  });

  ipcMain.handle('get-last-ocr', async () => {
    try {
      const p = path.join(REPO_ROOT, 'workspace', 'ocr-last-result.json');
      if (!fs.existsSync(p)) return { success: false, message: 'No saved OCR result yet.' };
      const data = JSON.parse(fs.readFileSync(p, 'utf-8'));
      return { success: true, result: data };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('clear-last-ocr', async () => {
    try {
      const p = path.join(REPO_ROOT, 'workspace', 'ocr-last-result.json');
      if (fs.existsSync(p)) fs.unlinkSync(p);
      lastOcrProgress = null;
      return { success: true };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('select-prints', async () => {
    const result = await dialog.showOpenDialog(win, {
      title: 'Select electrical prints (PDF / PNG)',
      filters: [
        { name: 'Prints', extensions: ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp'] },
        { name: 'All Files', extensions: ['*'] },
      ],
      properties: ['openFile', 'multiSelections'],
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, canceled: true, paths: [] };
    }
    return { success: true, paths: result.filePaths };
  });

  ipcMain.handle('list-conveyors', async () => {
    const r = await runPythonAsync([APPLY_SCRIPT, 'list-conveyors']);
    if (!r.ok) return { success: false, message: r.error };
    try {
      const conveyors = JSON.parse(r.stdout);
      return { success: true, conveyors };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('list-devices', async (_event, data) => {
    const args = [APPLY_SCRIPT, 'list-devices'];
    if (data?.category) args.push('--category', data.category);
    if (data?.machine) args.push('--machine', data.machine);
    const r = await runPythonAsync(args);
    if (!r.ok) return { success: false, message: r.error };
    try {
      const payload = JSON.parse(r.stdout);
      return { success: true, ...payload };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('export-plc', async (_event, data) => {
    try {
      const mode = data?.mode || 'archive';
      const args = [PLC_EXPORT_SCRIPT];
      if (mode === 'active') {
        args.push('export', '--use-active');
      } else {
        const archivePath = data?.archivePath;
        if (!archivePath || !fs.existsSync(archivePath)) {
          return { success: false, message: 'Archive not found. Drop or browse a RUN .tar.gz first.' };
        }
        args.push('import', archivePath);
      }
      if (data?.includeSpares) args.push('--include-spares');
      if (data?.prismSeed) args.push('--prism-seed');
      // maxFio: 0 / missing = complete scene (all I/O). Positive = rare debug cap only.
      const maxFio = data?.maxFio;
      if (maxFio == null || maxFio === '' || Number(maxFio) <= 0) {
        args.push('--max-fio', '0');
      } else {
        args.push('--max-fio', String(maxFio));
      }
      const r = await runPythonAsync(args);
      if (!r.ok) return { success: false, message: r.error };
      const result = JSON.parse(r.stdout);
      if (!result.ok) return { success: false, message: result.error || 'Export failed' };
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('autogen-inspect-excel', async (_event, data) => {
    try {
      const excel = data?.excel || data?.path;
      if (!excel || !fs.existsSync(excel)) {
        return { success: false, message: 'Excel file not found.' };
      }
      const r = await runPythonAsync([AUTOGEN_SCRIPT, 'inspect-excel', excel]);
      if (!r.ok) return { success: false, message: r.error };
      return { success: true, result: JSON.parse(r.stdout) };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  function parseAutogenStdout(stdout) {
    const raw = (stdout || '').trim();
    if (!raw) throw new Error('Empty response from autogen script');
    // Compact single-object JSON (normal path)
    try {
      return JSON.parse(raw);
    } catch (_) { /* may have stderr noise / multi-line */ }
    // IMPORTANT: use the FIRST '{' (root object), not lastIndexOf.
    // Preview/generate payloads nest conveyor objects; last '{' was a single
    // conveyor row → UI showed 0 conveyors while Inspect showed P127 fields.
    const start = raw.indexOf('{');
    if (start < 0) throw new Error(`No JSON in autogen output: ${raw.slice(0, 200)}`);
    let depth = 0;
    let end = -1;
    let inStr = false;
    let esc = false;
    for (let i = start; i < raw.length; i++) {
      const ch = raw[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\') esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') {
        inStr = true;
        continue;
      }
      if (ch === '{') depth += 1;
      else if (ch === '}') {
        depth -= 1;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
    }
    const slice = end > start ? raw.slice(start, end) : raw.slice(start);
    return JSON.parse(slice);
  }

  /** Resolve library path — UI often shows relative tools/libraries/... which fails from desktop/ cwd. */
  function resolveAutogenLibrary(lib) {
    const candidates = [];
    if (lib && String(lib).trim()) {
      const s = String(lib).trim();
      candidates.push(s);
      if (!path.isAbsolute(s)) {
        candidates.push(path.join(REPO_ROOT, s));
        candidates.push(path.join(REPO_ROOT, 'tools', 'libraries', path.basename(s)));
      }
    }
    candidates.push(DEFAULT_AUTOGEN_LIBRARY);
    candidates.push(path.join(REPO_ROOT, 'tools', 'libraries', 'OReilly_Library_v3.L5X'));
    for (const c of candidates) {
      try {
        if (c && fs.existsSync(c)) return c;
      } catch (_) { /* ignore */ }
    }
    return DEFAULT_AUTOGEN_LIBRARY;
  }

  function resolveActiveRunDir(preferred) {
    const candidates = [];
    if (preferred) candidates.push(preferred);
    candidates.push(path.join(REPO_ROOT, 'workspace', 'active', 'RUN'));
    candidates.push(path.join(REPO_ROOT, 'workspace', 'active', 'RUN', 'RUN'));
    candidates.push(path.join(REPO_ROOT, 'workspace', 'active_work', 'RUN'));
    // active-meta.json from last import (I/O & Prints tab)
    try {
      const meta = readJson(ACTIVE_META, null);
      if (meta?.run_dir) candidates.push(meta.run_dir);
      if (meta?.run_dir && path.basename(meta.run_dir) !== 'RUN') {
        candidates.push(path.join(meta.run_dir, 'RUN'));
      }
    } catch (_) { /* ignore */ }
    for (const c of candidates) {
      try {
        if (c && fs.existsSync(path.join(c, 'project.cfg'))) return c;
        if (c && fs.existsSync(path.join(c, 'FORTNA', 'Conveyor.asc'))) return c;
      } catch (_) { /* ignore */ }
    }
    return null;
  }

  /** If IPC/stdout fails after Python wrote files, recover the newest successful export. */
  function recoverLatestAutogenResult(maxAgeMs = 5 * 60 * 1000) {
    try {
      const root = path.join(REPO_ROOT, 'exports', 'autogen');
      if (!fs.existsSync(root)) return null;
      const dirs = fs.readdirSync(root, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => {
          const full = path.join(root, d.name);
          const st = fs.statSync(full);
          return { full, mtime: st.mtimeMs, name: d.name };
        })
        .sort((a, b) => b.mtime - a.mtime);
      const now = Date.now();
      for (const d of dirs.slice(0, 5)) {
        if (now - d.mtime > maxAgeMs) continue;
        const resultPath = path.join(d.full, 'autogen_result.json');
        const reportPath = path.join(d.full, 'autogen_report.json');
        const l5x = fs.readdirSync(d.full).find((f) => f.toLowerCase().endsWith('.l5x')
          && !/library|oreilly_library/i.test(f));
        if (fs.existsSync(resultPath)) {
          const r = JSON.parse(fs.readFileSync(resultPath, 'utf-8'));
          if (r.ok) return r;
        }
        if (l5x && fs.existsSync(reportPath)) {
          const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
          return {
            ok: true,
            engine: 'python',
            out_dir: d.full,
            l5x: path.join(d.full, l5x),
            report,
            recovered: true,
            note: 'Recovered from disk after IPC/stdout issue — L5X was written successfully.',
          };
        }
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  function slimAutogenResult(result) {
    if (!result || typeof result !== 'object') return result;
    const rep = result.report || {};
    return {
      ok: !!result.ok,
      engine: result.engine || 'python',
      out_dir: result.out_dir || '',
      l5x: result.l5x || '',
      report_txt: result.report_txt || '',
      library_used: result.library_used || '',
      recovered: !!result.recovered,
      l5x_bytes: result.l5x_bytes || 0,
      report: {
        project: rep.project,
        processor: rep.processor,
        revision: rep.revision,
        conveyor_count: rep.conveyor_count,
        area_count: rep.area_count,
        tag_count: rep.tag_count,
        program_count: rep.program_count,
        programs: rep.programs,
        areas_summary: rep.areas_summary,
        conveyor_sample: rep.conveyor_sample,
        template_usage: rep.template_usage,
        io_point_count: rep.io_point_count,
        io_module_count: rep.io_module_count,
        missing_excel_templates_in_library: rep.missing_excel_templates_in_library,
        note: rep.note,
      },
    };
  }

  ipcMain.handle('autogen-defaults', async () => {
    const runDir = resolveActiveRunDir(null);
    const meta = readJson(ACTIVE_META, null);
    return {
      success: true,
      engine: 'python',
      library: DEFAULT_AUTOGEN_LIBRARY,
      libraryExists: fs.existsSync(DEFAULT_AUTOGEN_LIBRARY),
      runDir: runDir || path.join(REPO_ROOT, 'workspace', 'active', 'RUN'),
      runLoaded: !!runDir,
      machine: meta?.machine || '',
      deviceCount: meta?.device_count || 0,
      note: 'Native Python autogen (fortna_autogen.py). Excel is optional legacy only.',
    };
  });

  ipcMain.handle('autogen-generate', async (_event, data) => {
    try {
      const mode = data?.mode || 'run'; // default: from tar.gz RUN (not Excel)
      const library = resolveAutogenLibrary(data?.library);
      if (!fs.existsSync(library)) {
        return {
          success: false,
          message: `Library L5X not found.\nTried: ${library}\nBrowse to tools/libraries/OReilly_Library_v3.L5X`,
        };
      }

      let args;
      let runDir = null;
      if (mode === 'run') {
        runDir = resolveActiveRunDir(data?.runDir);
        if (!runDir) {
          return {
            success: false,
            message:
              'No active RUN found from I/O & Prints.\n'
              + '1) Open I/O & Prints\n'
              + '2) Load a .tar.gz (status must show machine loaded)\n'
              + '3) Return here and click Generate from RUN\n'
              + '(Looked under workspace/active/RUN and active-meta.json)',
          };
        }
        args = [
          AUTOGEN_SCRIPT, 'from-run',
          '--run-dir', runDir,
          '--library', library,
          '--processor', data?.processor || '1756-L83E',
        ];
        // Optional gold programs from Autogen tab checkboxes
        const includePrograms = Array.isArray(data?.includePrograms)
          ? data.includePrograms
          : (typeof data?.includePrograms === 'string' && data.includePrograms
            ? data.includePrograms.split(/[,;]/).map((s) => s.trim()).filter(Boolean)
            : []);
        if (includePrograms.length) {
          args.push('--include-programs', includePrograms.join(','));
        }
        if (data?.noSys) args.push('--no-sys');
        // Default engine = RUN/tar.gz IO_MAP. Gold Excel only when user opts in.
        if (data?.ioMapGold || data?.includeIoMapGold) {
          args.push('--io-map-gold');
        } else {
          args.push('--no-io-map-gold');
        }
        // Dashboard workbook (Inputdata replacement) — save payload if provided
        let workbookPath = data?.workbookPath || AUTOGEN_WORKBOOK_PATH;
        if (data?.workbook && typeof data.workbook === 'object') {
          try {
            fs.mkdirSync(path.dirname(AUTOGEN_WORKBOOK_PATH), { recursive: true });
            fs.writeFileSync(
              AUTOGEN_WORKBOOK_PATH,
              JSON.stringify(data.workbook, null, 2),
              'utf8',
            );
            workbookPath = AUTOGEN_WORKBOOK_PATH;
          } catch (e) {
            return { success: false, message: `Failed to save workbook: ${e.message}` };
          }
        }
        if (workbookPath && fs.existsSync(workbookPath)) {
          args.push('--workbook', workbookPath);
        }
      } else {
        const excel = data?.excel || data?.path;
        if (!excel || !fs.existsSync(excel)) {
          return {
            success: false,
            message: 'Excel path is legacy only. Prefer Generate from RUN after loading tar.gz.',
          };
        }
        args = [AUTOGEN_SCRIPT, 'from-excel', excel, '--library', library];
      }
      if (data?.outDir) args.push('--out-dir', data.outDir);

      const r = await runPythonAsync(args, REPO_ROOT, {
        progressEvent: 'autogen-progress',
        win,
      });

      let result = null;
      if (r.ok) {
        try {
          result = parseAutogenStdout(r.stdout);
        } catch (parseErr) {
          // Python may have written L5X even if stdout parse failed
          result = recoverLatestAutogenResult();
          if (!result) {
            return {
              success: false,
              message: `Autogen finished but response parse failed: ${parseErr.message}`,
            };
          }
        }
      } else {
        // Recover if files were written before a non-zero exit / kill
        result = recoverLatestAutogenResult();
        if (!result) {
          try {
            const parsed = parseAutogenStdout(r.error || r.stdout || '');
            if (parsed.error) {
              return { success: false, message: parsed.error };
            }
          } catch (_) { /* ignore */ }
          const err = (r.error || '').toString();
          const short = err.length > 500 ? `${err.slice(0, 500)}…` : err;
          return {
            success: false,
            message: short || 'Autogen failed (no L5X written). Check RUN is loaded and library path.',
          };
        }
      }

      if (!result || result.ok === false) {
        return {
          success: false,
          message: (result && result.error) || 'Autogen failed',
        };
      }
      result.library_used = library;
      result.engine = result.engine || 'python';
      if (runDir) result.run_dir = runDir;
      return { success: true, result: slimAutogenResult(result) };
    } catch (e) {
      const recovered = recoverLatestAutogenResult();
      if (recovered) {
        return { success: true, result: slimAutogenResult(recovered) };
      }
      return { success: false, message: e.message || String(e) };
    }
  });

  ipcMain.handle('autogen-preview-run', async (_event, data) => {
    try {
      const runDir = resolveActiveRunDir(data?.runDir);
      if (!runDir) {
        return {
          success: false,
          message: 'No active RUN. Load a .tar.gz on I/O & Prints first (same package used by banks/devices).',
        };
      }
      const args = [
        AUTOGEN_SCRIPT, 'from-run',
        '--run-dir', runDir,
        '--preview-only',
        '--processor', data?.processor || '1756-L83E',
      ];
      const r = await runPythonAsync(args);
      if (!r.ok) {
        let msg = r.error || 'Preview failed';
        if (typeof msg === 'string' && msg.length > 400) msg = msg.slice(0, 400) + '…';
        return { success: false, message: msg };
      }
      const result = parseAutogenStdout(r.stdout);
      result.run_dir = runDir;
      result.engine = result.engine || 'python';
      // Drop full conveyor sample if huge — keep counts for UI
      if (Array.isArray(result.conveyors) && result.conveyors.length > 25) {
        result.conveyors = result.conveyors.slice(0, 25);
      }
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  // --- AutoGen workbook (Inputdata replacement: auto from RUN, editable) ---
  ipcMain.handle('autogen-workbook-build', async (_event, data) => {
    try {
      const runDir = resolveActiveRunDir(data?.runDir);
      if (!runDir) {
        return {
          success: false,
          message: 'No active RUN. Load a .tar.gz on I/O & Prints first.',
        };
      }
      const args = [
        WORKBOOK_SCRIPT, 'build',
        '--run-dir', runDir,
        '--processor', data?.processor || '1756-L83E',
        '--out', AUTOGEN_WORKBOOK_PATH,
      ];
      if (data?.mergeExisting !== false) args.push('--merge-existing');
      const r = await runPythonAsync(args, REPO_ROOT);
      if (!r.ok) {
        return { success: false, message: r.error || 'Workbook build failed' };
      }
      let result = null;
      try {
        result = JSON.parse((r.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop() || '{}');
      } catch (_) {
        return { success: false, message: 'Workbook build returned invalid JSON' };
      }
      if (!result.ok) {
        return { success: false, message: result.error || 'Workbook build failed' };
      }
      // Attach full conveyors from disk if Python slimmed stdout
      try {
        if (fs.existsSync(AUTOGEN_WORKBOOK_PATH)) {
          const full = JSON.parse(fs.readFileSync(AUTOGEN_WORKBOOK_PATH, 'utf8'));
          result.conveyors = full.conveyors || result.conveyors;
          result.io_points = full.io_points || result.io_points;
          result.modules = full.modules || result.modules;
          result.full_path = AUTOGEN_WORKBOOK_PATH;
        }
      } catch (_) { /* ignore */ }
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });

  ipcMain.handle('autogen-workbook-save', async (_event, data) => {
    try {
      const wb = data?.workbook;
      if (!wb || typeof wb !== 'object') {
        return { success: false, message: 'No workbook payload' };
      }
      fs.mkdirSync(path.dirname(AUTOGEN_WORKBOOK_PATH), { recursive: true });
      wb.saved_utc = new Date().toISOString();
      fs.writeFileSync(AUTOGEN_WORKBOOK_PATH, JSON.stringify(wb, null, 2), 'utf8');
      return { success: true, path: AUTOGEN_WORKBOOK_PATH };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });

  ipcMain.handle('autogen-workbook-load', async () => {
    try {
      if (!fs.existsSync(AUTOGEN_WORKBOOK_PATH)) {
        return { success: false, message: 'No workbook saved yet — click Build workbook from RUN' };
      }
      const wb = JSON.parse(fs.readFileSync(AUTOGEN_WORKBOOK_PATH, 'utf8'));
      return { success: true, workbook: wb, path: AUTOGEN_WORKBOOK_PATH };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });

  ipcMain.handle('autogen-verify', async () => {
    try {
      const runDir = resolveActiveRunDir(null);
      const library = resolveAutogenLibrary(null);
      const latest = recoverLatestAutogenResult(24 * 60 * 60 * 1000); // any today
      return {
        success: true,
        engine: 'python',
        script: AUTOGEN_SCRIPT,
        scriptExists: fs.existsSync(AUTOGEN_SCRIPT),
        workbookScript: WORKBOOK_SCRIPT,
        workbookPath: AUTOGEN_WORKBOOK_PATH,
        workbookExists: fs.existsSync(AUTOGEN_WORKBOOK_PATH),
        library,
        libraryExists: fs.existsSync(library),
        runDir,
        runLoaded: !!runDir,
        latestExport: latest
          ? {
              out_dir: latest.out_dir,
              l5x: latest.l5x,
              conveyor_count: latest.report?.conveyor_count,
              tag_count: latest.report?.tag_count,
            }
          : null,
        note: 'Primary path is Python fortna_autogen.py from-run (not Excel VBA).',
      };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  /** Pack Perspective components for Designer/gateway import (no full build required). */
  ipcMain.handle('ignition-pack-perspective', async (_event, data) => {
    try {
      const packScript = path.join(REPO_ROOT, 'tools', 'scripts', 'fortna_perspective_pack.py');
      // Connected merge-group pack (P500) + memory tags_import.json
      // Default conveyors: P440→P442→P444 + P542/P544 → P500 (P522 not in RUN)
      const defaultConvs = 'P440,P442,P444,P500,P542,P544,P540';
      const args = [
        packScript, 'pack',
        '--use-latest-symbols',
        '--max-conv', String(data?.nConv || 10),
        '--max-pe', String(data?.nPe || 12),
        '--canvas-w', String(data?.canvasW || 900),
        '--canvas-h', String(data?.canvasH || 1100),
        '--project-name', data?.projectName || 'FortnaPlus_POC',
        '--with-tags',
        '--conveyors', data?.conveyors || defaultConvs,
      ];
      if (data?.photoeyes) args.push('--photoeyes', data.photoeyes);
      if (data?.outDir) args.push('--out-dir', data.outDir);
      const r = await runPythonAsync(args);
      if (!r.ok) {
        try {
          const parsed = JSON.parse((r.error || r.stdout || '').trim());
          if (parsed.error) return { success: false, message: parsed.error };
        } catch (_) { /* ignore */ }
        return { success: false, message: r.error || 'Perspective pack failed' };
      }
      const raw = (r.stdout || '').trim();
      const start = raw.indexOf('{');
      if (start < 0) return { success: false, message: 'No JSON from perspective pack' };
      const result = JSON.parse(raw.slice(start));
      if (!result.ok) return { success: false, message: result.error || 'Pack failed' };
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });

  /** Ignition Build — layout SVG + tag/device seed from active RUN (not full .gwbk yet). */
  ipcMain.handle('ignition-build-layout', async (_event, data) => {
    try {
      const runDir = resolveActiveRunDir(data?.runDir);
      if (!runDir) {
        return {
          success: false,
          message: 'No active RUN. Load a .tar.gz on I/O & Prints first.',
        };
      }
      const poc = !!(data?.poc || data?.mode === 'poc');
      const args = poc
        ? [
            IGNITION_BUILD_SCRIPT, 'build-poc', '--run-dir', runDir,
            '--n-conv', String(data?.nConv || 10),
            '--n-pe', String(data?.nPe || 10),
          ]
        : [IGNITION_BUILD_SCRIPT, 'build', '--run-dir', runDir];
      const r = await runPythonAsync(args);
      if (!r.ok) {
        try {
          const parsed = JSON.parse((r.error || r.stdout || '').trim());
          if (parsed.error) return { success: false, message: parsed.error };
        } catch (_) { /* ignore */ }
        return { success: false, message: r.error || 'Ignition layout build failed' };
      }
      const raw = (r.stdout || '').trim();
      const start = raw.indexOf('{');
      if (start < 0) return { success: false, message: 'No JSON from ignition build script' };
      const result = JSON.parse(raw.slice(start));
      if (!result.ok) return { success: false, message: result.error || 'Build failed' };

      // Wow path: auto-deploy designer-safe project into gateway data/projects
      // (ProjectTest shell + RUN conveyors/PE — avoids white "no-project" canvas)
      // Use stamped project name when available so each deploy is trackable.
      let deploy = null;
      const stamp = result.folder_stamp || '';
      const projName = result.project_name
        || (stamp
          ? `FortnaPlus_${(result.machine || 'Machine').replace(/[^A-Za-z0-9_]/g, '')}_${stamp}`
          : 'FortnaPlus_ORNCCP5');
      const gwRoot = path.join(
        process.env['ProgramFiles'] || 'C:\\Program Files',
        'Inductive Automation',
        'Ignition',
        'data',
        'projects',
      );
      const gwProject = path.join(gwRoot, projName);
      if (fs.existsSync(IGNITION_DEPLOY_SAFE)) {
        try {
          const d = await runPythonAsync(
            [IGNITION_DEPLOY_SAFE, '--project-name', projName, '--out-dir', result.out_dir || ''],
            REPO_ROOT,
          );
          deploy = {
            ok: !!d.ok,
            stdout: (d.stdout || '').trim().slice(-500),
            error: d.error || '',
            gatewayProject: gwProject,
            project_name: projName,
            folder_stamp: stamp,
            out_dir: result.out_dir || '',
          };
          try {
            await runPythonAsync([
              path.join(REPO_ROOT, 'tools', 'scripts', 'fix_ignition_project_attrs.py'),
              '--path',
              gwProject,
            ], REPO_ROOT);
          } catch (_) { /* ignore */ }
        } catch (e) {
          deploy = { ok: false, error: e.message || String(e), project_name: projName, folder_stamp: stamp };
        }
      }
      result.gateway_deploy = deploy;
      result.note_ui = deploy?.ok
        ? `Built ${stamp || ''} → deployed gateway project ${projName}. Scan Filesystem → open Smoke_Test.`
        : `Built export ${result.out_dir || ''}. Deploy skipped/failed — see gateway_deploy.`;
      return { success: true, result };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });

  ipcMain.handle('autogen-select-excel', async () => {
    const result = await dialog.showOpenDialog(win, {
      title: 'Select PLC Autogen Excel workbook',
      filters: [
        { name: 'Excel Autogen', extensions: ['xlsm', 'xlsx'] },
        { name: 'All Files', extensions: ['*'] },
      ],
      properties: ['openFile'],
      defaultPath: path.join(REPO_ROOT, 'tools', 'libraries'),
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, canceled: true };
    }
    return { success: true, path: result.filePaths[0] };
  });

  ipcMain.handle('autogen-select-library', async () => {
    const result = await dialog.showOpenDialog(win, {
      title: 'Select AOI / template library L5X',
      filters: [
        { name: 'Studio 5000 L5X', extensions: ['L5X', 'l5x'] },
        { name: 'All Files', extensions: ['*'] },
      ],
      properties: ['openFile'],
      defaultPath: path.join(REPO_ROOT, 'tools', 'libraries'),
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, canceled: true };
    }
    return { success: true, path: result.filePaths[0] };
  });

  ipcMain.handle('apply-recipe', async (_event, data) => {
    try {
      const { recipeId, params = {}, repack = true } = data || {};
      if (recipeId === 'clone-device') {
        const device = params.selectedDevice || {};
        const args = [
          APPLY_SCRIPT,
          'clone-device',
          '--table', device.table || params.table || '',
          '--template', device.name || params.template || '',
          '--new-name', params.newName || '',
          '--offset-x', String(params.offsetX || 0),
          '--offset-y', String(params.offsetY || 0),
        ];
        if (params.cloneRelated === false) args.push('--no-related');
        if (repack) args.push('--repack');
        const r = runPython(args);
        if (!r.ok) return { success: false, message: r.error };
        const result = JSON.parse(r.stdout);
        return { success: true, result };
      }
      if (recipeId === 'add-photoeye') {
        const args = [APPLY_SCRIPT, 'add-photoeye', '--conveyor', params.conveyor || ''];
        if (params.peName) args.push('--pe-name', params.peName);
        if (params.ioWord) args.push('--io-word', params.ioWord);
        if (params.ioBit) args.push('--io-bit', params.ioBit);
        if (repack) args.push('--repack');
        const r = runPython(args);
        if (!r.ok) return { success: false, message: r.error };
        const result = JSON.parse(r.stdout);
        return { success: true, result };
      }
      if (recipeId === 'add-printer') {
        return {
          success: false,
          message: 'Printer recipe is documented only — use the how-to steps and linked P&A docs for manual configuration.',
          manual: true,
        };
      }
      return { success: false, message: `Unknown recipe: ${recipeId}` };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  ipcMain.handle('open-path', async (_event, targetPath) => {
    try {
      if (!targetPath) return { success: false, message: 'No path provided.' };
      let resolved = path.isAbsolute(targetPath)
        ? path.resolve(targetPath)
        : path.join(REPO_ROOT, targetPath);
      if (!fs.existsSync(resolved)) {
        const doc = resolveDocPath(targetPath);
        if (doc) resolved = doc;
      }
      if (!fs.existsSync(resolved)) {
        return { success: false, message: `Path not found: ${resolved}` };
      }
      const stat = fs.statSync(resolved);
      // Open files with default app (PDF viewer); folders in Explorer
      const err = await shell.openPath(resolved);
      if (err) return { success: false, message: err };
      return { success: true, path: resolved, isDirectory: stat.isDirectory() };
    } catch (e) {
      return { success: false, message: e.message };
    }
  });

  /** Open a print PDF, optionally at a page (Edge/Chrome/Acrobat best-effort). */
  ipcMain.handle('open-print-page', async (_event, data) => {
    try {
      let filePath = data?.path || data?.file || '';
      const page = Math.max(1, parseInt(data?.page, 10) || 1);
      if (!filePath) return { success: false, message: 'No print path' };
      if (!path.isAbsolute(filePath)) {
        // Resolve against workspace/prints and REPO_ROOT
        const candidates = [
          path.join(PRINTS_DIR, filePath),
          path.join(REPO_ROOT, filePath),
          path.join(REPO_ROOT, 'workspace', 'prints', filePath),
        ];
        // Also search by basename under prints/
        const base = path.basename(filePath);
        if (fs.existsSync(PRINTS_DIR)) {
          const walk = (dir, depth = 0) => {
            if (depth > 4) return null;
            try {
              for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
                const full = path.join(dir, ent.name);
                if (ent.isFile() && ent.name.toLowerCase() === base.toLowerCase()) return full;
                if (ent.isDirectory()) {
                  const hit = walk(full, depth + 1);
                  if (hit) return hit;
                }
              }
            } catch (_) { /* ignore */ }
            return null;
          };
          const found = walk(PRINTS_DIR);
          if (found) candidates.unshift(found);
        }
        filePath = candidates.find((p) => fs.existsSync(p)) || filePath;
      }
      if (!fs.existsSync(filePath)) {
        return { success: false, message: `Print not found: ${filePath}` };
      }

      // Best-effort open *at page*. Success depends on the installed PDF viewer:
      //   Edge/Chrome: file:///...#page=N
      //   Adobe Acrobat/Reader: /A "page=N"
      //   SumatraPDF: -page N
      // Fallback: open whole PDF and tell user the page number.
      const { execFile, spawn } = require('child_process');
      const fileUri = `file:///${filePath.replace(/\\/g, '/')}#page=${page}`;

      const trySpawn = (cmd, args) => new Promise((resolve) => {
        try {
          const child = spawn(cmd, args, { detached: true, stdio: 'ignore', windowsHide: true });
          child.on('error', () => resolve(false));
          child.unref();
          // If spawn didn't emit error immediately, assume launch ok
          setTimeout(() => resolve(true), 250);
        } catch (_) {
          resolve(false);
        }
      });

      const edgePaths = [
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      ];
      const chromePaths = [
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      ];
      const adobePaths = [
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Adobe', 'Acrobat DC', 'Acrobat', 'Acrobat.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Adobe', 'Acrobat Reader DC', 'Reader', 'AcroRd32.exe'),
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Adobe', 'Acrobat Reader DC', 'Reader', 'AcroRd32.exe'),
      ];
      const sumatraPaths = [
        path.join(process.env.LOCALAPPDATA || '', 'SumatraPDF', 'SumatraPDF.exe'),
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'SumatraPDF', 'SumatraPDF.exe'),
      ];

      const firstExisting = (list) => list.find((p) => p && fs.existsSync(p));

      if (page > 1) {
        const sumatra = firstExisting(sumatraPaths);
        if (sumatra) {
          const ok = await trySpawn(sumatra, ['-page', String(page), filePath]);
          if (ok) {
            return {
              success: true, path: filePath, page, jumped: true,
              note: `Opened at page ${page} (SumatraPDF)`,
            };
          }
        }
        const adobe = firstExisting(adobePaths);
        if (adobe) {
          const ok = await trySpawn(adobe, ['/A', `page=${page}`, filePath]);
          if (ok) {
            return {
              success: true, path: filePath, page, jumped: true,
              note: `Opened at page ${page} (Adobe)`,
            };
          }
        }
        const edge = firstExisting(edgePaths);
        if (edge) {
          const ok = await trySpawn(edge, [fileUri]);
          if (ok) {
            return {
              success: true, path: filePath, page, jumped: true,
              note: `Opened at page ${page} (Edge)`,
            };
          }
        }
        const chrome = firstExisting(chromePaths);
        if (chrome) {
          const ok = await trySpawn(chrome, [fileUri]);
          if (ok) {
            return {
              success: true, path: filePath, page, jumped: true,
              note: `Opened at page ${page} (Chrome)`,
            };
          }
        }
      }

      // Default association — whole file (page jump not guaranteed)
      const err = await shell.openPath(filePath);
      if (err) {
        return new Promise((resolve) => {
          execFile('cmd', ['/c', 'start', '', filePath], { windowsHide: true }, (e2) => {
            if (e2) resolve({ success: false, message: e2.message || err });
            else {
              resolve({
                success: true, path: filePath, page, jumped: false,
                note: page > 1
                  ? `Opened PDF — jump to page ${page} in your viewer (default app has no page API)`
                  : 'Opened PDF',
              });
            }
          });
        });
      }
      return {
        success: true,
        path: filePath,
        page,
        jumped: false,
        note: page > 1
          ? `Opened PDF — jump to page ${page} in your viewer (install Edge/Adobe/Sumatra for auto page jump)`
          : 'Opened PDF',
      };
    } catch (e) {
      return { success: false, message: e.message || String(e) };
    }
  });
}

if (gotSingleInstanceLock) {
  app.whenReady().then(createWindow);

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}