const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');

const DASHBOARD_FILE = process.env.ROCKWELL_DASHBOARD || 'index.html';
const IS_PROJECT_INTAKE = DASHBOARD_FILE.includes('project-intake');
const IS_PRISM = DASHBOARD_FILE.includes('prism');

// Keep Electron cache/userData in a writable per-user folder (avoids Access Denied when
// cwd is protected, e.g. system32, or when Git + Intake run at the same time).
function configureElectronStorage() {
  const appFolder = IS_PROJECT_INTAKE ? 'ProjectIntake' : IS_PRISM ? 'PRISM' : 'RockwellGit';
  const root = path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    'RockwellGitDashboard',
    appFolder
  );
  const diskCache = path.join(root, 'disk-cache');
  const gpuCache = path.join(root, 'gpu-cache');

  for (const dir of [root, diskCache, gpuCache]) {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch (e) {
      console.warn('[electron] could not create storage dir:', dir, e.message);
    }
  }

  // Recover from Chromium "Critical error found -8" / missing cache entry (harmless but noisy).
  try {
    const cacheIndex = path.join(diskCache, 'index');
    if (fs.existsSync(cacheIndex)) {
      const stat = fs.statSync(cacheIndex);
      if (stat.size === 0) fs.rmSync(diskCache, { recursive: true, force: true });
    }
  } catch (e) {
    try { fs.rmSync(diskCache, { recursive: true, force: true }); } catch (_) { /* ignore */ }
  }
  try { fs.mkdirSync(diskCache, { recursive: true }); } catch (_) { /* ignore */ }

  try {
    app.setPath('userData', root);
    app.setPath('sessionData', path.join(root, 'session'));
  } catch (e) {
    console.warn('[electron] setPath failed:', e.message);
  }

  app.commandLine.appendSwitch('disk-cache-dir', diskCache);
  app.commandLine.appendSwitch('gpu-cache-dir', gpuCache);
}

configureElectronStorage();

function sanitizeDemoFolderName(name) {
  const cleaned = (name || 'default')
    .replace(/[^A-Za-z0-9_-]/g, '_')
    .replace(/^_+|_+$/g, '')
    .substring(0, 80);
  return cleaned || 'default';
}

const INTAKE_OUTPUT_ROOT = 'intake-outputs';
const LEGACY_INTAKE_ROOT = 'demo-intake-outputs';
const MERGED_OUTPUT_ROOT = 'merged-outputs';
const LEGACY_MERGED_OUTPUT_ROOT = 'demo-merged-outputs';

const intakeOutputRoot = () => path.join(__dirname, '..', INTAKE_OUTPUT_ROOT);
const mergedOutputRoot = () => path.join(__dirname, '..', MERGED_OUTPUT_ROOT);

function mergedSiteDir(systemName) {
  const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(systemName));
  return { siteDir: path.join(mergedOutputRoot(), siteFolder), siteFolder };
}

function resolveMergedFileCandidate(system, safeName) {
  const root = path.join(__dirname, '..');
  const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(system));
  for (const folder of [MERGED_OUTPUT_ROOT, LEGACY_MERGED_OUTPUT_ROOT]) {
    const candidate = path.join(root, folder, siteFolder, safeName);
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function resolveWorktreeTextFilePath(system, filename) {
  if (!filename) return null;
  const root = path.join(__dirname, '..');
  const safeName = path.basename(filename);
  const folders = ['routines', 'aois', 'udts', 'programs', 'tags', 'tasks'];

  if (system) {
    for (const folder of folders) {
      const candidate = path.join(root, 'systems', system, 'source', folder, safeName);
      if (fs.existsSync(candidate)) return candidate;
    }
    const mergedCandidate = resolveMergedFileCandidate(system, safeName);
    if (mergedCandidate) return mergedCandidate;
  }

  const systemsRoot = path.join(root, 'systems');
  if (fs.existsSync(systemsRoot)) {
    for (const sysDir of fs.readdirSync(systemsRoot)) {
      for (const folder of folders) {
        const candidate = path.join(systemsRoot, sysDir, 'source', folder, safeName);
        if (fs.existsSync(candidate)) return candidate;
      }
    }
  }

  for (const folder of [MERGED_OUTPUT_ROOT, LEGACY_MERGED_OUTPUT_ROOT]) {
    const mergedRoot = path.join(root, folder);
    if (!fs.existsSync(mergedRoot)) continue;
    for (const siteDir of fs.readdirSync(mergedRoot)) {
      const candidate = path.join(mergedRoot, siteDir, safeName);
      if (fs.existsSync(candidate)) return candidate;
    }
  }

  const outputsRoot = path.join(root, 'stored-xml-outputs');
  if (fs.existsSync(outputsRoot)) {
    const suffix = `_${safeName}`;
    const matches = fs.readdirSync(outputsRoot)
      .filter(name => name.toLowerCase().endsWith(suffix.toLowerCase()) || name === safeName)
      .map(name => ({
        full: path.join(outputsRoot, name),
        mtime: fs.statSync(path.join(outputsRoot, name)).mtimeMs
      }))
      .sort((a, b) => b.mtime - a.mtime);
    if (matches.length > 0) return matches[0].full;
  }

  return null;
}

function resolveBaselinePathForMerge(system, masterFileName) {
  const root = path.join(__dirname, '..');
  const { siteDir } = mergedSiteDir(system || 'default');

  if (masterFileName) {
    const direct = resolveWorktreeTextFilePath(system, masterFileName);
    if (direct) return direct;
  }

  if (fs.existsSync(siteDir)) {
    try {
      const rootFiles = fs.readdirSync(siteDir)
        .filter(name => /\.(l5x|xml)$/i.test(name))
        .map(name => ({
          name,
          full: path.join(siteDir, name),
          mtime: fs.statSync(path.join(siteDir, name)).mtimeMs
        }))
        .sort((a, b) => b.mtime - a.mtime);
      if (rootFiles.length > 0) return rootFiles[0].full;
    } catch (e) {
      // ignore
    }
  }

  const systemsRoot = path.join(root, 'systems');
  if (system && fs.existsSync(systemsRoot)) {
    const sysDir = path.join(systemsRoot, system, 'source', 'routines');
    if (fs.existsSync(sysDir)) {
      try {
        const controllerLike = fs.readdirSync(sysDir)
          .filter(name => /\.(l5x|xml)$/i.test(name))
          .filter(name => !/^RT_/i.test(name) && !/^merged-/i.test(name))
          .map(name => ({
            full: path.join(sysDir, name),
            mtime: fs.statSync(path.join(sysDir, name)).mtimeMs
          }))
          .sort((a, b) => b.mtime - a.mtime);
        if (controllerLike.length > 0) return controllerLike[0].full;
      } catch (e) {
        // ignore
      }
    }
  }

  return null;
}

function resolveStagedUploadPath(system, author, routineName) {
  const { siteDir } = mergedSiteDir(system || 'default');
  const uploadsDir = path.join(siteDir, 'uploads');
  if (!fs.existsSync(uploadsDir)) return null;

  const safeAuthor = sanitizeDemoFolderName(author || 'unknown');
  const safeRoutine = sanitizeDemoFolderName(routineName || 'routine');
  const expected = path.join(uploadsDir, `${safeAuthor}_${safeRoutine}.l5x`);
  if (fs.existsSync(expected)) return expected;

  try {
    const routineLower = (routineName || '').toLowerCase();
    const authorLower = (author || '').toLowerCase();
    for (const name of fs.readdirSync(uploadsDir)) {
      if (!/\.(l5x|xml)$/i.test(name)) continue;
      const lower = name.toLowerCase();
      if (routineLower && lower.includes(routineLower) && authorLower && lower.includes(authorLower)) {
        return path.join(uploadsDir, name);
      }
    }
  } catch (e) {
    // ignore
  }
  return null;
}

function sanitizeSystemName(system) {
  return (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
}

function intakeTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function intakeRelativePath(siteFolder, subPath = '') {
  const base = `${INTAKE_OUTPUT_ROOT}/${siteFolder}`;
  return subPath ? `${base}/${subPath.replace(/\\/g, '/')}` : base;
}

function intakeExportDir(siteDir, phase) {
  return path.join(siteDir, 'exports', phase);
}

function archiveIntakePhaseIfExists(siteDir, phase) {
  const exportDir = intakeExportDir(siteDir, phase);
  if (!fs.existsSync(exportDir)) return null;
  const hasFiles = fs.readdirSync(exportDir).some((name) => {
    const fp = path.join(exportDir, name);
    return fs.statSync(fp).isFile();
  });
  if (!hasFiles) return null;
  const archiveDir = path.join(siteDir, 'archive', intakeTimestamp(), phase);
  fs.mkdirSync(archiveDir, { recursive: true });
  copyDirFilesTo(exportDir, archiveDir);
  return archiveDir;
}

function ensureIntakeSiteDir(systemName) {
  const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(systemName));
  const siteDir = path.join(intakeOutputRoot(), siteFolder);
  [
    '',
    'exports/acade-io',
    'exports/rough-program',
    'exports/spatial',
    'exports/emulation',
    'layouts',
    'archive',
  ].forEach((sub) => fs.mkdirSync(path.join(siteDir, sub), { recursive: true }));
  return { siteDir, siteFolder };
}

function resolveScaffoldFioArea(scaffoldDir, requestedArea) {
  const clean = (name) => String(name || '').replace(/[^A-Za-z0-9_-]/g, '_');
  if (requestedArea && String(requestedArea).trim()) {
    return clean(requestedArea);
  }
  const manifestPath = path.join(scaffoldDir, 'scaffold_manifest.json');
  if (fs.existsSync(manifestPath)) {
    try {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      const scores = new Map();
      const order = [];
      const noteArea = (rawArea, routines) => {
        const area = clean(rawArea);
        if (!area) return;
        if (!scores.has(area)) {
          scores.set(area, { photoeyes: 0, tags: 0 });
          order.push(area);
        }
        const bucket = scores.get(area);
        for (const r of routines || []) {
          const count = r.tag_count || (r.tags || []).length || 0;
          bucket.tags += count;
          if (r.device_class === 'Photoeye') bucket.photoeyes += count;
        }
      };
      for (const entry of manifest.areas || []) {
        noteArea(entry.area || entry.name?.replace(/^PG_/i, ''), entry.routines);
      }
      for (const prog of manifest.programs || []) {
        const area = clean(prog.area || prog.name?.replace(/^PG_/i, ''));
        if (area && !scores.has(area)) {
          scores.set(area, { photoeyes: 0, tags: prog.tag_count || 0 });
          order.push(area);
        }
        noteArea(prog.area || prog.name?.replace(/^PG_/i, ''), prog.routines);
      }
      if (order.length) {
        const ranked = order
          .map((area) => ({ area, ...scores.get(area) }))
          .sort((a, b) => b.photoeyes - a.photoeyes || b.tags - a.tags);
        const best = ranked.find((r) => r.photoeyes > 0) || ranked[0];
        if (best?.area) return best.area;
      }
    } catch (_) { /* fall through */ }
  }
  const bindingsPath = path.join(scaffoldDir, 'factory_io_bindings.csv');
  if (fs.existsSync(bindingsPath)) {
    try {
      const lines = fs.readFileSync(bindingsPath, 'utf8').split(/\r?\n/).filter(Boolean);
      if (lines.length > 1) {
        const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
        const areaCol = headers.indexOf('area');
        const dcCol = headers.indexOf('device_class');
        if (areaCol >= 0) {
          const seen = new Map();
          for (const line of lines.slice(1)) {
            const cols = line.split(',');
            const a = clean(cols[areaCol]?.trim());
            if (!a) continue;
            if (!seen.has(a)) seen.set(a, { photoeyes: 0, tags: 0 });
            const bucket = seen.get(a);
            bucket.tags += 1;
            if (dcCol >= 0 && cols[dcCol]?.trim() === 'Photoeye') bucket.photoeyes += 1;
          }
          const ranked = [...seen.entries()]
            .map(([area, stats]) => ({ area, ...stats }))
            .sort((a, b) => b.photoeyes - a.photoeyes || b.tags - a.tags);
          const best = ranked.find((r) => r.photoeyes > 0) || ranked[0];
          if (best?.area) return best.area;
        }
      }
    } catch (_) { /* fall through */ }
  }
  return '';
}

function intakeProfileSlugId(text) {
  return String(text || 'profile')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 40) || 'profile';
}

function findExcelInIntakeFolder(folder) {
  if (!folder || !fs.existsSync(folder)) return '';
  const names = ['PLC.xls', 'PLC.xlsx', 'PLC.xlsm', 'plc.xls', 'plc.xlsx', 'PLC.csv'];
  for (const name of names) {
    const candidate = path.join(folder, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  return '';
}

function findL5xInIntakeFolder(folder, system) {
  if (!folder || !fs.existsSync(folder)) return '';
  const sys = sanitizeSystemName(system);
  const names = [
    'PLC.l5x', 'PLC.L5X', 'PLC.xml', 'PLC.XML',
    `${sys}.L5X`, `${sys}.l5x`, `${sys}.xml`, `${sys}.XML`,
  ];
  for (const name of names) {
    const candidate = path.join(folder, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  const found = new Set();
  walkDirForL5x(folder, sys, found, 0, 3);
  return Array.from(found)[0] || '';
}

function buildIntakeProfileFromSiteDir(siteDir, siteFolder) {
  const sys = siteFolder;
  const excelPath = findExcelInIntakeFolder(siteDir);
  const l5xPath = findL5xInIntakeFolder(siteDir, sys);

  const acadeDir = intakeExportDir(siteDir, 'acade-io');
  const scaffoldDir = intakeExportDir(siteDir, 'rough-program');
  const spatialDir = intakeExportDir(siteDir, 'spatial');

  const summaryPath = path.join(acadeDir, 'summary.json');
  let lastImportAt = null;
  let lastSummaryPath = '';
  let lastOutputDir = '';
  let importStats = null;
  if (fs.existsSync(summaryPath)) {
    lastSummaryPath = summaryPath;
    lastOutputDir = acadeDir;
    lastImportAt = fs.statSync(summaryPath).mtime.toISOString();
    try {
      const summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
      if (summary?.success) {
        if (summary.generated_at) lastImportAt = summary.generated_at;
        importStats = {
          points: summary.preview_row_count || summary.row_count || 0,
          modules: summary.module_count || 0,
          inputs: summary.input_count || 0,
          outputs: summary.output_count || 0,
        };
      }
    } catch (_) { /* ignore */ }
  }

  const manifestPath = path.join(scaffoldDir, 'scaffold_manifest.json');
  let lastScaffoldAt = null;
  let lastScaffoldDir = '';
  if (fs.existsSync(manifestPath)) {
    lastScaffoldAt = fs.statSync(manifestPath).mtime.toISOString();
    lastScaffoldDir = scaffoldDir;
  }

  const spatialPath = path.join(spatialDir, 'spatial_layout.json');
  let lastSpatialAt = null;
  let lastSpatialDir = '';
  if (fs.existsSync(spatialPath)) {
    lastSpatialAt = fs.statSync(spatialPath).mtime.toISOString();
    lastSpatialDir = spatialDir;
  }

  return {
    id: intakeProfileSlugId(sys),
    name: sys.replace(/_/g, ' '),
    system: sys,
    named: true,
    projectFolder: siteDir,
    excelPath,
    l5xPath,
    lastImportAt,
    lastSummaryPath,
    lastOutputDir,
    lastScaffoldAt,
    lastScaffoldDir,
    lastSpatialAt,
    lastSpatialDir,
    importStats,
  };
}

function discoverIntakeSitesFromDisk() {
  const root = intakeOutputRoot();
  if (!fs.existsSync(root)) return [];
  const sites = [];
  for (const name of fs.readdirSync(root)) {
    if (name.startsWith('.')) continue;
    const siteDir = path.join(root, name);
    try {
      if (!fs.statSync(siteDir).isDirectory()) continue;
    } catch (_) {
      continue;
    }
    sites.push(buildIntakeProfileFromSiteDir(siteDir, name));
  }
  return sites.sort((a, b) =>
    a.system.localeCompare(b.system, undefined, { sensitivity: 'base' }));
}

function mergeDiscoveredIntakeProfiles(store) {
  const base = store && typeof store === 'object'
    ? { version: store.version || 1, activeId: store.activeId || '', profiles: [...(store.profiles || [])] }
    : { version: 1, activeId: '', profiles: [] };

  const discovered = discoverIntakeSitesFromDisk();
  let addedCount = 0;
  for (const d of discovered) {
    const idx = base.profiles.findIndex((p) =>
      p.id === d.id
      || p.system === d.system
      || (p.projectFolder && path.normalize(p.projectFolder) === path.normalize(d.projectFolder)));
    if (idx < 0) {
      base.profiles.push(d);
      addedCount += 1;
      continue;
    }
    const p = base.profiles[idx];
    if (!p.projectFolder) p.projectFolder = d.projectFolder;
    if (!p.excelPath && d.excelPath) p.excelPath = d.excelPath;
    if (!p.l5xPath && d.l5xPath) p.l5xPath = d.l5xPath;
    if (!p.lastImportAt && d.lastImportAt) {
      p.lastImportAt = d.lastImportAt;
      p.lastSummaryPath = d.lastSummaryPath || p.lastSummaryPath;
      p.lastOutputDir = d.lastOutputDir || p.lastOutputDir;
      p.importStats = d.importStats || p.importStats;
    }
    if (!p.lastScaffoldAt && d.lastScaffoldAt) {
      p.lastScaffoldAt = d.lastScaffoldAt;
      p.lastScaffoldDir = d.lastScaffoldDir || p.lastScaffoldDir;
    }
    if (!p.lastSpatialAt && d.lastSpatialAt) {
      p.lastSpatialAt = d.lastSpatialAt;
      p.lastSpatialDir = d.lastSpatialDir || p.lastSpatialDir;
    }
    if (p.named === undefined) p.named = !!(p.system && String(p.system).trim());
  }

  base.profiles.sort((a, b) =>
    (a.system || '').localeCompare(b.system || '', undefined, { sensitivity: 'base' }));

  if (!base.activeId && base.profiles.length) {
    base.activeId = base.profiles[0].id;
  } else if (base.activeId && !base.profiles.some((p) => p.id === base.activeId)) {
    base.activeId = base.profiles[0]?.id || '';
  }

  return { store: base, discoveredCount: discovered.length, addedCount };
}

function copyDirFilesTo(srcDir, destDir) {
  if (!srcDir || !fs.existsSync(srcDir)) return destDir;
  fs.mkdirSync(destDir, { recursive: true });
  fs.readdirSync(srcDir).forEach((name) => {
    const src = path.join(srcDir, name);
    if (fs.statSync(src).isFile()) {
      fs.copyFileSync(src, path.join(destDir, name));
    }
  });
  return destDir;
}

function findPythonExecutable() {
  // Electron spawn() needs a real .exe path (not "py") when shell:false.
  const exists = (p) => p && fs.existsSync(p);

  if (process.platform === 'win32') {
    try {
      const resolved = spawnSync(
        'py',
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', shell: true, windowsHide: true }
      );
      if (resolved.status === 0 && resolved.stdout) {
        const exe = resolved.stdout.trim().split(/\r?\n/).pop().trim();
        if (exists(exe)) return exe;
      }
    } catch (e) {
      // try fallbacks
    }

    try {
      const wherePy = spawnSync('where', ['python'], { encoding: 'utf8', shell: true, windowsHide: true });
      if (wherePy.status === 0 && wherePy.stdout) {
        for (const line of wherePy.stdout.split(/\r?\n/)) {
          const candidate = line.trim();
          if (exists(candidate) && !candidate.toLowerCase().includes('windowsapps')) {
            return candidate;
          }
        }
      }
    } catch (e) {
      // try fallbacks
    }

    const localAppData = process.env.LOCALAPPDATA || '';
    if (localAppData) {
      const searchRoots = [
        path.join(localAppData, 'Programs', 'Python'),
        path.join(localAppData, 'Python'),
      ];
      for (const pythonRoot of searchRoots) {
        if (!exists(pythonRoot)) continue;
        try {
          const versions = fs.readdirSync(pythonRoot)
            .filter((name) => name.toLowerCase().includes('python'))
            .sort()
            .reverse();
          for (const ver of versions) {
            const exe = path.join(pythonRoot, ver, 'python.exe');
            if (exists(exe)) return exe;
          }
        } catch (e) {
          // ignore
        }
      }
    }
  }

  const pythonCandidates = process.platform === 'win32'
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];

  for (const cmd of pythonCandidates) {
    try {
      const result = spawnSync(cmd, ['--version'], { encoding: 'utf8', shell: true, windowsHide: true });
      if (result.status === 0 || (result.stdout && result.stdout.toLowerCase().includes('python'))) {
        if (cmd.includes(path.sep) && exists(cmd)) return cmd;
        if (cmd === 'py' || cmd === 'python' || cmd === 'python3') {
          // Last resort: shell mode only — caller must use shell:true
          return cmd;
        }
      }
    } catch (e) {
      // try next
    }
  }
  return null;
}

function spawnPython(pythonExe, args, env) {
  // Never use shell:true on Windows — it breaks paths with spaces (e.g. "FMS For Amazon")
  // and Python reports "No PDF files found." with exit code 1.
  return spawn(pythonExe, args, {
    shell: false,
    env: env || process.env,
    windowsHide: true,
  });
}

function findTesseractExecutable() {
  const candidates = process.platform === 'win32'
    ? [
        'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
        'C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe',
      ]
    : [];

  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }

  try {
    const whereTess = spawnSync('where', ['tesseract'], { encoding: 'utf8', shell: true, windowsHide: true });
    if (whereTess.status === 0 && whereTess.stdout) {
      const first = whereTess.stdout.trim().split(/\r?\n/)[0].trim();
      if (first && fs.existsSync(first)) return first;
    }
  } catch (e) {
    // not on PATH
  }
  return null;
}

function buildPythonEnv() {
  const env = { ...process.env };
  env.PYTHONIOENCODING = 'utf-8';
  env.PYTHONUTF8 = '1';
  const tess = findTesseractExecutable();
  if (tess && tess.includes(path.sep)) {
    const tessDir = path.dirname(tess);
    env.PATH = `${tessDir}${path.delimiter}${env.PATH || ''}`;
    if (!env.TESSDATA_PREFIX) {
      env.TESSDATA_PREFIX = path.join(tessDir, 'tessdata');
    }
  }
  return env;
}

function systemNameFromPdfPath(pdfPath) {
  const base = path.basename(pdfPath, path.extname(pdfPath));
  const stripped = base.replace(/[_\s-]?(prints?|drawings?|electrical).*$/i, '');
  const m = stripped.match(/([A-Za-z0-9]+(?:_[A-Za-z0-9]+)+)/);
  return m ? m[1] : stripped;
}

function walkDirForL5x(dir, sysName, found, depth, maxDepth) {
  if (depth > maxDepth || !dir || !fs.existsSync(dir)) return;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    return;
  }
  const targetL5x = `${sysName}.l5x`;
  const targetXml = `${sysName}.xml`;
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isFile()) {
      const lower = ent.name.toLowerCase();
      if (lower === targetL5x.toLowerCase() || lower === targetXml.toLowerCase()) {
        found.add(path.resolve(full));
      }
    } else if (ent.isDirectory()) {
      walkDirForL5x(full, sysName, found, depth + 1, maxDepth);
    }
  }
}

function collectL5xSearchDirs(pdfPaths, explicitDirs, l5xFolder) {
  const dirs = new Set();
  const add = (p) => {
    if (!p) return;
    const norm = path.normalize(p);
    if (fs.existsSync(norm)) dirs.add(norm);
  };

  (explicitDirs || []).forEach(add);
  if (l5xFolder) add(l5xFolder);

  (pdfPaths || []).forEach((pdfPath) => {
    if (!pdfPath) return;
    const dir = path.dirname(pdfPath);
    add(dir);
    add(path.dirname(dir));
    add(path.join(dir, '..', 'Git Test'));
    add(path.join(dir, '..', 'Programs'));
    add(path.join(dir, '..', 'New Imports'));
    add(path.join(dir, '..', '..', 'Git Test'));
  });

  return Array.from(dirs);
}

function discoverCompanionL5x(pdfPaths, searchDirs, l5xFolder) {
  const found = new Set();
  const dirs = collectL5xSearchDirs(pdfPaths, searchDirs, l5xFolder);
  const uniqueDirs = [...new Set(dirs.map((d) => path.resolve(d)))];

  for (const pdfPath of pdfPaths || []) {
    const sysName = systemNameFromPdfPath(pdfPath);
    if (!sysName) continue;
    const names = [
      `${sysName}.L5X`,
      `${sysName}.l5x`,
      `${sysName}.xml`,
      `${sysName}.XML`,
    ];

    for (const dir of uniqueDirs) {
      if (!fs.existsSync(dir)) continue;
      for (const name of names) {
        const candidate = path.join(dir, name);
        if (fs.existsSync(candidate)) {
          found.add(path.resolve(candidate));
        }
      }
      walkDirForL5x(dir, sysName, found, 0, 4);
    }
  }

  const unique = [];
  const seen = new Set();
  for (const p of found) {
    const key = path.resolve(p).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(path.resolve(p));
  }
  return unique;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1500,
    height: 980,
    minWidth: 1200,
    minHeight: 750,
    backgroundColor: '#09090b', // Deep dark to match dashboard
    title: IS_PROJECT_INTAKE ? 'Project Intake' : IS_PRISM ? 'PRISM' : 'Rockwell Git',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false
    },
    show: false,
    frame: false,           // Fully custom titlebar - super clean look
    autoHideMenuBar: true,
    resizable: true,
    transparent: false,
  });

  // Load the dashboard (index.html or project-intake.html via ROCKWELL_DASHBOARD env)
  const dashboardPath = path.join(__dirname, '..', 'dashboard', DASHBOARD_FILE);
  win.loadFile(dashboardPath);

  // Remove default menu
  Menu.setApplicationMenu(null);

  // Custom window controls via IPC
  ipcMain.on('window-minimize', () => win.minimize());
  ipcMain.on('window-maximize', () => {
    if (win.isMaximized()) {
      win.unmaximize();
    } else {
      win.maximize();
    }
  });
  ipcMain.on('window-close', () => win.close());

  // Real merge integration - calls the Python script with file contents from dashboard
  // This can be triggered from the dashboard UI (Electron only)
  ipcMain.handle('run-real-merge', async (event, data) => {
    try {
      const {
        routineName,
        baselineContent,
        change1Content,
        change2Content,
        system,
        masterFileName,
        change1Author,
        change2Author,
        useDiskBaseline
      } = data || {};

      // Create a temp directory for this merge
      const tempDir = path.join(os.tmpdir(), `rockwell-real-merge-${Date.now()}`);
      fs.mkdirSync(tempDir, { recursive: true });

      const basePath = path.join(tempDir, 'baseline.l5x');
      const c1Path = path.join(tempDir, 'change1.l5x');
      const c2Path = path.join(tempDir, 'change2.l5x');
      const outPath = path.join(tempDir, `merged-${routineName || 'routine'}.l5x`);

      let baselineReady = false;
      if (useDiskBaseline !== false) {
        const diskBaseline = resolveBaselinePathForMerge(system, masterFileName);
        if (diskBaseline && fs.existsSync(diskBaseline)) {
          fs.copyFileSync(diskBaseline, basePath);
          baselineReady = true;
        }
      }
      if (!baselineReady) {
        if (!baselineContent) {
          return {
            success: false,
            message: 'No baseline .L5X/.XML found. Drop your master export in the Import Pipeline (or select it as Master Snapshot), then try again.',
            log: masterFileName ? `Looked for: ${masterFileName}` : ''
          };
        }
        fs.writeFileSync(basePath, baselineContent, 'utf8');
      }

      let c1Ready = false;
      let c2Ready = false;
      if (useDiskBaseline !== false) {
        const diskC1 = resolveStagedUploadPath(system, change1Author, routineName);
        const diskC2 = resolveStagedUploadPath(system, change2Author, routineName);
        if (diskC1 && fs.existsSync(diskC1)) {
          fs.copyFileSync(diskC1, c1Path);
          c1Ready = true;
        }
        if (diskC2 && fs.existsSync(diskC2)) {
          fs.copyFileSync(diskC2, c2Path);
          c2Ready = true;
        }
      }
      if (!c1Ready) {
        if (!change1Content) {
          return { success: false, message: 'Missing first person\'s uploaded routine content.' };
        }
        fs.writeFileSync(c1Path, change1Content, 'utf8');
      }
      if (!c2Ready) {
        if (!change2Content) {
          return { success: false, message: 'Missing second person\'s uploaded routine content.' };
        }
        fs.writeFileSync(c2Path, change2Content, 'utf8');
      }

      // Path to the merger script (relative to project root)
      const scriptPath = path.join(__dirname, '..', 'tools', 'scripts', 'merge_l5x_routines.py');

      // NOTE: We auto-detect 'py' (Windows launcher) or 'python3'/'python'.
      // The script requires lxml: pip install lxml

      // Find a working Python command.
      // On Windows, prefer the 'py' launcher over 'python' (avoids Microsoft Store stub).
      const pythonCandidates = process.platform === 'win32'
        ? ['py', 'python', 'python3']
        : ['python3', 'python'];

      const pythonExe = findPythonExecutable();

      if (!pythonExe) {
        return {
          success: false,
          message: 'Python not found. Please install from https://python.org (recommended) and check "Add Python to PATH" during install. Restart the app after. On Windows the "py" launcher is often more reliable.',
          log: ''
        };
      }

      const args = [
        scriptPath,
        basePath,
        c1Path,
        c2Path,
        '--routine', routineName || '',
        '--output', outPath,
        '--output-format', 'routine'
      ];

      return await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        child.on('close', (code) => {
          let finalMessage = stdout.trim();
          if (stderr) finalMessage += '\n' + stderr.trim();

          if (code === 0 && fs.existsSync(outPath)) {
            // Copy merged result to merged-outputs/<siteName>/merged-<Routine>.l5x
            const { siteDir, siteFolder } = mergedSiteDir(system || 'default');
            fs.mkdirSync(siteDir, { recursive: true });

            const finalOut = path.join(siteDir, path.basename(outPath));
            fs.copyFileSync(outPath, finalOut);

            // Also write the merged result to the real source folder for the system (so it reflects in program .xml)
            if (system) {
              const routinesDir = path.join(__dirname, '..', 'systems', system, 'source', 'routines');
              fs.mkdirSync(routinesDir, { recursive: true });
              const srcTarget = path.join(routinesDir, path.basename(outPath));
              fs.copyFileSync(outPath, srcTarget);
            }

            // Always store a copy in the dedicated easy-to-track folder at worktree root
            const outputsRoot = path.join(__dirname, '..', 'stored-xml-outputs');
            fs.mkdirSync(outputsRoot, { recursive: true });
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const storedName = `${system || 'unknown'}_realmerged_${timestamp}_${path.basename(outPath)}`;
            const storedTarget = path.join(outputsRoot, storedName);
            fs.copyFileSync(outPath, storedTarget);

            // Clean temp
            try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch(e) {}

            resolve({
              success: true,
              message: 'Real merge completed successfully!',
              outputPath: finalOut,
              alsoStoredAtWorktreeRoot: storedTarget,
              log: finalMessage
            });
          } else {
            let msg = `Merge process exited with code ${code}.`;
            if (finalMessage.toLowerCase().includes('python') && finalMessage.toLowerCase().includes('not found')) {
              msg = 'Python not found. Install from https://python.org (check "Add Python to PATH") and restart the app. On Windows the "py" launcher is often more reliable.';
            }
            resolve({
              success: false,
              message: msg,
              log: finalMessage
            });
          }
        });
      });
    } catch (err) {
      return { success: false, message: err.message || 'Unknown error running real merge.' };
    }
  });

  // Stage dropped files into merged-outputs/<siteName>/...
  // kind: master = baseline .L5X at site root | upload = branch change in uploads/
  ipcMain.handle('stage-demo-merged-output', async (event, data) => {
    try {
      const { fileName, content, siteName, kind, author, routineName } = data || {};
      if (!content || !fileName) {
        return { success: false, message: 'Missing file content or name.' };
      }

      const lower = fileName.toLowerCase();
      if (!lower.endsWith('.l5x') && !lower.endsWith('.xml')) {
        return { success: false, message: `Only .L5X/.XML files are staged to ${MERGED_OUTPUT_ROOT}/.` };
      }

      const siteFolder = sanitizeDemoFolderName(siteName || fileName.replace(/\.(l5x|xml)$/i, ''));
      const siteDir = path.join(mergedOutputRoot(), siteFolder);
      fs.mkdirSync(siteDir, { recursive: true });

      const stageKind = (kind || 'master').toLowerCase();
      let outPath;
      let outName;

      if (stageKind === 'upload') {
        const uploadsDir = path.join(siteDir, 'uploads');
        fs.mkdirSync(uploadsDir, { recursive: true });
        const safeAuthor = sanitizeDemoFolderName(author || 'unknown');
        let routineLabel = (routineName || '').trim();
        if (!routineLabel) {
          routineLabel = fileName.replace(/\.(l5x|xml)$/i, '');
        }
        const safeRoutine = sanitizeDemoFolderName(routineLabel);
        outName = `${safeAuthor}_${safeRoutine}.l5x`;
        outPath = path.join(uploadsDir, outName);
        // Re-upload from same person updates their file
        fs.writeFileSync(outPath, content, 'utf8');
        return {
          success: true,
          skipped: false,
          outputPath: outPath,
          siteFolder,
          message: `Upload saved: ${siteFolder}/uploads/${outName}`
        };
      }

      // master: keep original dropped filename in the site folder root
      outName = path.basename(fileName);
      outPath = path.join(siteDir, outName);

      if (fs.existsSync(outPath)) {
        return {
          success: true,
          skipped: true,
          outputPath: outPath,
          siteFolder,
          message: `Already exists: ${siteFolder}/${outName}`
        };
      }

      fs.writeFileSync(outPath, content, 'utf8');
      return {
        success: true,
        skipped: false,
        outputPath: outPath,
        siteFolder,
        message: `Master saved: ${siteFolder}/${outName}`
      };
    } catch (err) {
      return { success: false, message: err.message || 'Failed to stage demo output.' };
    }
  });

  // Save dropped files to the real repo folder structure when pipeline is run
  ipcMain.handle('save-dropped-files', async (event, system, dropped) => {
    try {
      if (!system || !Array.isArray(dropped) || dropped.length === 0) {
        return { success: false, message: 'No files or system provided.' };
      }
      const root = path.join(__dirname, '..');
      let savedCount = 0;

      // Primary location: the real repo structure
      for (const f of dropped) {
        if (!f.content || !f.name) continue;
        let folder = 'routines';
        const lname = f.name.toLowerCase();
        if (lname.includes('aoi') || lname.includes('addon') || lname.includes('instruction')) {
          folder = 'aois';
        } else if (lname.includes('udt') || lname.includes('datatype')) {
          folder = 'udts';
        }
        const dir = path.join(root, 'systems', system, 'source', folder);
        fs.mkdirSync(dir, { recursive: true });
        const target = path.join(dir, f.name);
        fs.writeFileSync(target, f.content, 'utf8');
        savedCount++;
      }

      // Easy-to-track location inside the worktree root (dedicated outputs folder)
      const outputsRoot = path.join(root, 'stored-xml-outputs');
      fs.mkdirSync(outputsRoot, { recursive: true });
      for (const f of dropped) {
        if (!f.content || !f.name) continue;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const storedName = `${system}_${timestamp}_${f.name}`;
        const storedTarget = path.join(outputsRoot, storedName);
        fs.writeFileSync(storedTarget, f.content, 'utf8');
      }

      return { success: true, saved: savedCount, location: `systems/${system}/source/ (also copied to stored-xml-outputs/ at worktree root)` };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  // Read a baseline .L5X/.XML from the worktree when in-memory dropped files were cleared
  // (e.g. after Run Full Pipeline saved them to disk).
  ipcMain.handle('read-worktree-file', async (event, system, filename) => {
    try {
      if (!filename) {
        return { success: false, message: 'No filename provided.' };
      }

      const root = path.join(__dirname, '..');
      const safeName = path.basename(filename);
      const folders = ['routines', 'aois', 'udts', 'programs', 'tags', 'tasks'];

      // 1. Primary repo structure
      if (system) {
        for (const folder of folders) {
          const candidate = path.join(root, 'systems', system, 'source', folder, safeName);
          if (fs.existsSync(candidate)) {
            return { success: true, content: fs.readFileSync(candidate, 'utf8'), path: candidate };
          }
        }
      }

      // 2. Search all systems if the named system did not have the file
      const systemsRoot = path.join(root, 'systems');
      if (fs.existsSync(systemsRoot)) {
        for (const sysDir of fs.readdirSync(systemsRoot)) {
          for (const folder of folders) {
            const candidate = path.join(systemsRoot, sysDir, 'source', folder, safeName);
            if (fs.existsSync(candidate)) {
              return { success: true, content: fs.readFileSync(candidate, 'utf8'), path: candidate };
            }
          }
        }
      }

      // 3. Rockwell Git merge staging folder (merged-outputs/<site>/)
      if (system) {
        const mergedCandidate = resolveMergedFileCandidate(system, safeName);
        if (mergedCandidate) {
          return { success: true, content: fs.readFileSync(mergedCandidate, 'utf8'), path: mergedCandidate };
        }
      }
      for (const folder of [MERGED_OUTPUT_ROOT, LEGACY_MERGED_OUTPUT_ROOT]) {
        const mergedRoot = path.join(root, folder);
        if (!fs.existsSync(mergedRoot)) continue;
        for (const siteDir of fs.readdirSync(mergedRoot)) {
          const candidate = path.join(mergedRoot, siteDir, safeName);
          if (fs.existsSync(candidate)) {
            return { success: true, content: fs.readFileSync(candidate, 'utf8'), path: candidate };
          }
        }
      }

      // 4. Latest timestamped copy in stored-xml-outputs (pipeline writes here)
      const outputsRoot = path.join(root, 'stored-xml-outputs');
      if (fs.existsSync(outputsRoot)) {
        const suffix = `_${safeName}`;
        const matches = fs.readdirSync(outputsRoot)
          .filter(name => name.toLowerCase().endsWith(suffix.toLowerCase()) || name === safeName)
          .map(name => ({
            name,
            full: path.join(outputsRoot, name),
            mtime: fs.statSync(path.join(outputsRoot, name)).mtimeMs
          }))
          .sort((a, b) => b.mtime - a.mtime);

        if (matches.length > 0) {
          const best = matches[0];
          return { success: true, content: fs.readFileSync(best.full, 'utf8'), path: best.full };
        }
      }

      return {
        success: false,
        message: `Could not find "${safeName}" in systems/, ${MERGED_OUTPUT_ROOT}/, or stored-xml-outputs/.`,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  // Write a merged branch change to the real source .xml (used for "merge the branches" reflection)
  ipcMain.handle('write-branch-merge', async (event, system, program, content) => {
    try {
      if (!system || !program || !content) {
        return { success: false, message: 'Missing data for branch merge write.' };
      }
      const root = path.join(__dirname, '..');
      const dir = path.join(root, 'systems', system, 'source', 'routines');
      fs.mkdirSync(dir, { recursive: true });
      const target = path.join(dir, `${program}.L5X`);
      fs.writeFileSync(target, content, 'utf8');

      // Also store a copy in the easy-to-track worktree root location
      const outputsRoot = path.join(root, 'stored-xml-outputs');
      fs.mkdirSync(outputsRoot, { recursive: true });
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const storedName = `${system}_merged_${timestamp}_${program}.L5X`;
      const storedTarget = path.join(outputsRoot, storedName);
      fs.writeFileSync(storedTarget, content, 'utf8');

      return { success: true, path: target, alsoStored: storedTarget };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('select-pdf-folder', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select folder containing PDF prints',
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, path: null, files: [] };
    }
    const folder = result.filePaths[0];
    const files = fs.readdirSync(folder)
      .filter(name => name.toLowerCase().endsWith('.pdf'))
      .map(name => ({ name, path: path.join(folder, name) }));
    return { success: true, path: folder, files };
  });

  ipcMain.handle('select-l5x-folder', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select folder containing Studio 5000 .L5X exports',
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, path: null };
    }
    return { success: true, path: result.filePaths[0] };
  });

  ipcMain.handle('select-l5x-file', async (event, data) => {
    const { defaultDir, system } = data || {};
    const sys = (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
    const defaultPath = defaultDir && fs.existsSync(defaultDir)
      ? (['PLC.l5x', 'PLC.L5X', `${sys}.L5X`].map((n) => path.join(defaultDir, n)).find((p) => fs.existsSync(p))
          || path.join(defaultDir, 'PLC.l5x'))
      : undefined;
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      title: 'Select Studio 5000 L5X export',
      defaultPath,
      filters: [
        { name: 'Studio 5000 Export (*.L5X)', extensions: ['l5x', 'L5X'] },
        { name: 'All Files (*.*)', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, path: null };
    }
    return { success: true, path: result.filePaths[0] };
  });

  ipcMain.handle('find-l5x-file', async (event, data) => {
    try {
      const { folder, system } = data || {};
      if (!folder || !fs.existsSync(folder)) {
        return { success: false, path: null };
      }
      const sys = (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
      const names = [
        'PLC.l5x', 'PLC.L5X', 'PLC.xml', 'PLC.XML',
        `${sys}.L5X`, `${sys}.l5x`, `${sys}.xml`, `${sys}.XML`,
      ];
      for (const name of names) {
        const candidate = path.join(folder, name);
        if (fs.existsSync(candidate)) {
          return { success: true, path: candidate };
        }
      }
      const found = new Set();
      walkDirForL5x(folder, sys, found, 0, 3);
      const first = Array.from(found)[0];
      return first ? { success: true, path: first } : { success: false, path: null };
    } catch (err) {
      return { success: false, path: null, message: err.message };
    }
  });

  ipcMain.handle('discover-l5x', async (event, data) => {
    try {
      const { pdfPaths, searchDirs, l5xFolder } = data || {};
      const paths = (pdfPaths || []).filter((p) => p && fs.existsSync(p));
      const dirs = collectL5xSearchDirs(paths, searchDirs, l5xFolder);
      const found = discoverCompanionL5x(paths, searchDirs, l5xFolder);
      return { success: true, found, searchDirs: dirs };
    } catch (err) {
      return { success: false, found: [], message: err.message };
    }
  });

  ipcMain.handle('list-pdfs-in-folder', async (event, folderPath) => {
    try {
      if (!folderPath || !fs.existsSync(folderPath)) {
        return { success: false, message: 'Folder not found.', files: [] };
      }
      const files = fs.readdirSync(folderPath)
        .filter(name => name.toLowerCase().endsWith('.pdf'))
        .map(name => ({ name, path: path.join(folderPath, name), size: fs.statSync(path.join(folderPath, name)).size }));
      return { success: true, path: folderPath, files };
    } catch (err) {
      return { success: false, message: err.message, files: [] };
    }
  });

  // Extract PLC I/O from PDF prints (Project Intake dashboard)
  ipcMain.handle('extract-pdf-io', async (event, data) => {
    try {
      const {
        files, filePaths, system, outputCsv, outputXml, useOcr, ocrMaxPages,
        searchDirs, searchL5x, l5xFolder,
      } = data || {};
      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return {
          success: false,
          message: 'Python not found. Install from https://python.org and run: pip install pdfplumber pymupdf pandas lxml pillow',
        };
      }

      const tess = findTesseractExecutable();
      if (useOcr !== false && !tess) {
        return {
          success: false,
          message: 'Tesseract OCR not found. Re-run Launch-ProjectIntake.bat (it auto-installs), or install from https://github.com/UB-Mannheim/tesseract/wiki. For MGE9 MCP prints, also place the matching .L5X file (e.g. MGE9_MCP05.L5X) in the project folder.',
        };
      }

      const root = path.join(__dirname, '..');
      const scriptPath = path.join(root, 'tools', 'scripts', 'extract_plc_io_from_pdf.py');
      let pdfPaths = [];

      if (Array.isArray(filePaths) && filePaths.length > 0) {
        pdfPaths = filePaths.filter(p => p && fs.existsSync(p) && p.toLowerCase().endsWith('.pdf'));
      } else if (Array.isArray(files) && files.length > 0) {
        const tempDir = path.join(os.tmpdir(), `rockwell-pdf-io-${Date.now()}`);
        fs.mkdirSync(tempDir, { recursive: true });
        for (const f of files) {
          if (!f.name || !f.base64) continue;
          const safeName = path.basename(f.name);
          const target = path.join(tempDir, safeName);
          fs.writeFileSync(target, Buffer.from(f.base64, 'base64'));
          pdfPaths.push(target);
        }
      }

      if (!pdfPaths.length) {
        return { success: false, message: 'No PDF files provided. Use Browse Folder or drop smaller PDFs.' };
      }

      const sys = (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const outputDir = path.join(root, 'stored-pdf-outputs', `${sys}_${timestamp}`);
      fs.mkdirSync(outputDir, { recursive: true });

      const outBaseName = `${sys}_io`;
      const summaryPath = path.join(outputDir, 'summary.json');

      const args = [
        scriptPath,
        ...pdfPaths,
        '--system', sys,
        '--out', outBaseName,
        '--out-dir', outputDir,
        '--summary-json', summaryPath,
      ];

      if (!outputCsv) args.push('--no-csv');
      if (!outputXml) args.push('--no-xml');
      const autoOcr = useOcr !== false;
      if (autoOcr) args.push('--ocr');
      if (searchL5x === false) args.push('--no-search-l5x');
      if (ocrMaxPages) args.push('--ocr-max-pages', String(ocrMaxPages));

      const l5xSearchDirs = collectL5xSearchDirs(pdfPaths, searchDirs, l5xFolder);
      l5xSearchDirs.forEach((dir) => {
        args.push('--search-dir', dir);
      });

      const discoveredL5x = searchL5x !== false
        ? discoverCompanionL5x(pdfPaths, searchDirs, l5xFolder)
        : [];
      discoveredL5x.forEach((l5xPath) => {
        args.push('--l5x', l5xPath);
      });

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({
            code: -1,
            stdout,
            stderr: [stderr, err && err.message].filter(Boolean).join('\n'),
          });
        });
        child.on('close', (code) => {
          resolve({ code, stdout, stderr });
        });
      });

      let summary = null;
      if (fs.existsSync(summaryPath)) {
        summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
      }

      const csvPath = path.join(outputDir, outBaseName + '.csv');
      const xmlPath = path.join(outputDir, outBaseName + '.xml');
      const csvContent = outputCsv && fs.existsSync(csvPath) ? fs.readFileSync(csvPath, 'utf8') : null;
      const xmlContent = outputXml && fs.existsSync(xmlPath) ? fs.readFileSync(xmlPath, 'utf8') : null;

      if (!summary || !summary.success) {
        let failMsg = (summary && summary.message)
          || 'No I/O extracted. Place matching .L5X in Git Test\\ (e.g. MGE9_MCP05.L5X) or enable OCR.';
        if (discoveredL5x.length === 0 && searchL5x !== false) {
          failMsg += `\n\nNo .L5X files found. Searched:\n  ${l5xSearchDirs.join('\n  ')}`;
          if (l5xFolder) failMsg += `\nL5X folder: ${l5xFolder}`;
        } else if (discoveredL5x.length > 0) {
          failMsg += `\n\nL5X found but yielded no I/O: ${discoveredL5x.map((p) => path.basename(p)).join(', ')}`;
        }
        const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
        if (runResult.code !== 0) {
          failMsg += `\n\nPython exited with code ${runResult.code}.`;
          if (pyLog.includes('No PDF files found')) {
            failMsg += '\nPDF path was not passed correctly to Python (often paths with spaces). Retry after relaunching the app.';
          } else if (pyLog.includes('Neither pdfplumber nor pymupdf')) {
            failMsg += '\nRun Launch-ProjectIntake.bat to install Python dependencies.';
          } else if (pyLog.trim()) {
            failMsg += `\n\n${pyLog.trim().slice(0, 800)}`;
          }
        }
        return {
          success: false,
          message: failMsg,
          summary: summary || null,
          discoveredL5x,
          searchDirs: l5xSearchDirs,
          pythonExe,
          log: pyLog,
          outputDir,
        };
      }

      // Also copy into systems/<system>/exports/pdf-io/ when system name provided
      if (sys && sys !== 'project') {
        const sysExportDir = path.join(root, 'systems', sys, 'exports', 'pdf-io');
        fs.mkdirSync(sysExportDir, { recursive: true });
        if (csvContent) fs.writeFileSync(path.join(sysExportDir, path.basename(csvPath)), csvContent, 'utf8');
        if (xmlContent) fs.writeFileSync(path.join(sysExportDir, path.basename(xmlPath)), xmlContent, 'utf8');
        fs.writeFileSync(path.join(sysExportDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8');
      }

      return {
        success: true,
        summary,
        csvContent,
        xmlContent,
        outputDir,
        discoveredL5x,
        log: [runResult.stdout, runResult.stderr].filter(Boolean).join('\n'),
      };
    } catch (err) {
      return { success: false, message: err.message || 'PDF extraction failed.' };
    }
  });

  ipcMain.handle('find-export-file', async (event, folder) => {
    try {
      if (!folder || !fs.existsSync(folder)) {
        return { success: false, path: null };
      }
      const names = ['PLC.xls', 'PLC.xlsx', 'plc.xls', 'plc.xlsx', 'PLC.csv'];
      for (const name of names) {
        const candidate = path.join(folder, name);
        if (fs.existsSync(candidate)) {
          return { success: true, path: candidate };
        }
      }
      return { success: false, path: null };
    } catch (err) {
      return { success: false, path: null, message: err.message };
    }
  });

  ipcMain.handle('select-acade-file', async (event, defaultDir) => {
    const defaultPath = defaultDir && fs.existsSync(defaultDir)
      ? path.join(defaultDir, 'PLC.xls')
      : undefined;
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      title: 'Select AutoCAD Electrical PLC I/O export',
      defaultPath,
      filters: [
        { name: 'Excel 97-2003 Workbook (*.xls)', extensions: ['xls'] },
        { name: 'Excel Workbook (*.xlsx)', extensions: ['xlsx'] },
        { name: 'Excel Macro-Enabled (*.xlsm)', extensions: ['xlsm'] },
        { name: 'CSV (*.csv)', extensions: ['csv'] },
        { name: 'All spreadsheets', extensions: ['xls', 'xlsx', 'xlsm', 'csv'] },
        { name: 'All Files (*.*)', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths.length) {
      return { success: false, path: null };
    }
    return { success: true, path: result.filePaths[0] };
  });

  const intakeProfilesPath = () => path.join(__dirname, '..', 'systems', 'intake-profiles.json');

  ipcMain.handle('ensure-intake-project-folder', async (event, data) => {
    try {
      const { systemName } = data || {};
      const { siteDir, siteFolder } = ensureIntakeSiteDir(systemName);
      const relativePath = intakeRelativePath(siteFolder);
      return {
        success: true,
        projectFolder: siteDir,
        siteFolder,
        relativePath,
        message: `Project folder ready: ${relativePath}`,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Could not create project folder.' };
    }
  });

  ipcMain.handle('stage-demo-intake-file', async (event, data) => {
    try {
      const { systemName, sourcePath, fileName, content } = data || {};
      const { siteDir, siteFolder } = ensureIntakeSiteDir(systemName);
      let outName = fileName || (sourcePath ? path.basename(sourcePath) : '');
      if (!outName) {
        return { success: false, message: 'Missing file name.' };
      }
      outName = path.basename(outName);
      const outPath = path.join(siteDir, outName);

      if (sourcePath && fs.existsSync(sourcePath)) {
        fs.copyFileSync(sourcePath, outPath);
      } else if (content != null) {
        fs.writeFileSync(outPath, content, 'utf8');
      } else {
        return { success: false, message: 'Missing file path or content.' };
      }

      const relativePath = intakeRelativePath(siteFolder, outName);
      return {
        success: true,
        outputPath: outPath,
        projectFolder: siteDir,
        siteFolder,
        relativePath,
        message: `Staged: ${relativePath}`,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Failed to stage intake file.' };
    }
  });

  ipcMain.handle('load-intake-profiles', async () => {
    try {
      const p = intakeProfilesPath();
      let store = { version: 1, activeId: '', profiles: [] };
      if (fs.existsSync(p)) {
        store = JSON.parse(fs.readFileSync(p, 'utf8'));
      }
      const { store: merged, discoveredCount, addedCount } = mergeDiscoveredIntakeProfiles(store);
      if (discoveredCount > 0) {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, JSON.stringify(merged, null, 2), 'utf8');
      }
      return { success: true, store: merged, discoveredCount, addedCount };
    } catch (err) {
      return { success: false, message: err.message, store: { version: 1, activeId: '', profiles: [] } };
    }
  });

  ipcMain.handle('save-intake-profiles', async (event, store) => {
    try {
      const p = intakeProfilesPath();
      fs.mkdirSync(path.dirname(p), { recursive: true });
      fs.writeFileSync(p, JSON.stringify(store, null, 2), 'utf8');
      return { success: true, path: p };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('load-intake-cache', async (event, data) => {
    try {
      const { system, summaryPath: preferredSummary } = data || {};
      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const { siteDir } = ensureIntakeSiteDir(sys);
      const acadeDir = intakeExportDir(siteDir, 'acade-io');
      const scaffoldDir = intakeExportDir(siteDir, 'rough-program');
      const legacyAcadeDir = path.join(root, LEGACY_INTAKE_ROOT, sys, 'exports', 'acade-io');
      const legacyScaffoldDir = path.join(root, LEGACY_INTAKE_ROOT, sys, 'exports', 'rough-program');
      const systemsAcadeDir = path.join(root, 'systems', sys, 'exports', 'acade-io');
      const systemsScaffoldDir = path.join(root, 'systems', sys, 'exports', 'rough-program');
      const readIf = (fp) => (fs.existsSync(fp) ? fs.readFileSync(fp, 'utf8') : null);

      let summaryPath = preferredSummary && fs.existsSync(preferredSummary)
        ? preferredSummary
        : path.join(acadeDir, 'summary.json');
      for (const candidate of [
        summaryPath,
        path.join(legacyAcadeDir, 'summary.json'),
        path.join(systemsAcadeDir, 'summary.json'),
      ]) {
        if (fs.existsSync(candidate)) {
          summaryPath = candidate;
          break;
        }
      }
      let summary = null;
      if (fs.existsSync(summaryPath)) {
        try {
          summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
        } catch (e) {
          summary = null;
        }
      }

      const resolveAcadeDir = () => {
        if (fs.existsSync(path.join(acadeDir, 'summary.json'))) return acadeDir;
        if (fs.existsSync(path.join(legacyAcadeDir, 'summary.json'))) return legacyAcadeDir;
        if (fs.existsSync(systemsAcadeDir)) return systemsAcadeDir;
        return acadeDir;
      };
      const activeAcadeDir = resolveAcadeDir();
      let csvPath = path.join(activeAcadeDir, `${sys}_io.csv`);
      let xmlPath = path.join(activeAcadeDir, `${sys}_io.xml`);
      if (!fs.existsSync(csvPath) && fs.existsSync(activeAcadeDir)) {
        const csvFile = fs.readdirSync(activeAcadeDir).find((n) => n.endsWith('_io.csv'));
        if (csvFile) csvPath = path.join(activeAcadeDir, csvFile);
      }
      if (!fs.existsSync(xmlPath) && fs.existsSync(activeAcadeDir)) {
        const xmlFile = fs.readdirSync(activeAcadeDir).find((n) => n.endsWith('_io.xml'));
        if (xmlFile) xmlPath = path.join(activeAcadeDir, xmlFile);
      }

      const csvContent = readIf(csvPath);
      const xmlContent = readIf(xmlPath);

      const activeScaffoldDir = fs.existsSync(path.join(scaffoldDir, 'scaffold_manifest.json'))
        ? scaffoldDir
        : (fs.existsSync(path.join(legacyScaffoldDir, 'scaffold_manifest.json'))
          ? legacyScaffoldDir
          : systemsScaffoldDir);
      const manifestPath = path.join(activeScaffoldDir, 'scaffold_manifest.json');
      let scaffold = null;
      if (fs.existsSync(manifestPath)) {
        scaffold = {
          manifest: JSON.parse(fs.readFileSync(manifestPath, 'utf8')),
          l5x: readIf(path.join(activeScaffoldDir, 'scaffold.L5X')),
          csv: readIf(path.join(activeScaffoldDir, 'scaffold_tags.csv')),
          fio: readIf(path.join(activeScaffoldDir, 'factory_io_bindings.csv')),
          xml: readIf(path.join(activeScaffoldDir, 'scaffold_program.xml')),
          savedDir: activeScaffoldDir,
          l5xDiff: null,
        };
        const diffPath = path.join(activeScaffoldDir, 'l5x_diff.json');
        if (fs.existsSync(diffPath)) {
          scaffold.l5xDiff = JSON.parse(fs.readFileSync(diffPath, 'utf8'));
        }
      }

      return {
        success: true,
        hasImport: !!(summary && summary.success),
        summary,
        summaryPath: fs.existsSync(summaryPath) ? summaryPath : '',
        csvContent,
        xmlContent,
        outputDir: fs.existsSync(activeAcadeDir) ? activeAcadeDir : '',
        scaffold,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('extract-acade-io', async (event, data) => {
    try {
      const { filePath, l5xPath, system, outputCsv, outputXml, l5xFolder, searchDirs } = data || {};
      if (!filePath || !fs.existsSync(filePath)) {
        return { success: false, message: 'Spreadsheet file not found. Browse to the ACAD-E Excel export first.' };
      }
      if (!l5xPath || !fs.existsSync(l5xPath)) {
        return { success: false, message: 'L5X file not found. Browse to your Studio 5000 .L5X export before importing.' };
      }

      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return {
          success: false,
          message: 'Python not found. Install from https://python.org and run Launch-ProjectIntake.bat.',
        };
      }

      const root = path.join(__dirname, '..');
      const scriptPath = path.join(root, 'tools', 'scripts', 'extract_plc_io_from_acade.py');
      const sys = (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
      archiveIntakePhaseIfExists(siteDir, 'acade-io');
      const outputDir = intakeExportDir(siteDir, 'acade-io');
      fs.mkdirSync(outputDir, { recursive: true });

      const outBaseName = `${sys}_io`;
      const summaryPath = path.join(outputDir, 'summary.json');
      const args = [
        scriptPath,
        filePath,
        '--system', sys,
        '--out', outBaseName,
        '--out-dir', outputDir,
        '--summary-json', summaryPath,
      ];
      if (!outputCsv) args.push('--no-csv');
      if (!outputXml) args.push('--no-xml');

      args.push('--l5x', l5xPath);
      const discoveredL5x = [path.resolve(l5xPath)];

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({
            code: -1,
            stdout,
            stderr: [stderr, err && err.message].filter(Boolean).join('\n'),
          });
        });
        child.on('close', (code) => {
          resolve({ code, stdout, stderr });
        });
      });

      let summary = null;
      if (fs.existsSync(summaryPath)) {
        summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
      }

      const csvPath = path.join(outputDir, outBaseName + '.csv');
      const xmlPath = path.join(outputDir, outBaseName + '.xml');
      const csvContent = outputCsv && fs.existsSync(csvPath) ? fs.readFileSync(csvPath, 'utf8') : null;
      const xmlContent = outputXml && fs.existsSync(xmlPath) ? fs.readFileSync(xmlPath, 'utf8') : null;
      const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');

      if (!summary || !summary.success) {
        let failMsg = (summary && summary.message) || 'AutoCAD Electrical import failed.';
        if (runResult.code !== 0) {
          failMsg += `\n\nPython exited with code ${runResult.code}.`;
          if (pyLog.includes('openpyxl')) {
            failMsg += '\nRun Launch-ProjectIntake.bat to install openpyxl for Excel files.';
          } else if (pyLog.trim()) {
            failMsg += `\n\n${pyLog.trim().slice(0, 800)}`;
          }
        }
        return { success: false, message: failMsg, summary, log: pyLog, outputDir };
      }

      return {
        success: true,
        summary,
        summaryPath,
        csvContent,
        xmlContent,
        outputDir,
        projectFolder: siteDir,
        relativePath: intakeRelativePath(siteFolder, 'exports/acade-io'),
        discoveredL5x,
        log: pyLog,
      };
    } catch (err) {
      return { success: false, message: err.message || 'AutoCAD Electrical import failed.' };
    }
  });

  const layoutsDirForSystem = (root, system) => (
    path.join(ensureIntakeSiteDir(system).siteDir, 'layouts')
  );

  const readLayoutManifest = (layoutsDir) => {
    const manifestPath = path.join(layoutsDir, 'layout_manifest.json');
    if (!fs.existsSync(manifestPath)) return { manifest: {}, manifestPath };
    try {
      return { manifest: JSON.parse(fs.readFileSync(manifestPath, 'utf8')), manifestPath };
    } catch (e) {
      return { manifest: {}, manifestPath };
    }
  };

  const writeLayoutManifest = (manifestPath, manifest) => {
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');
  };

  const listLayoutFolder = (layoutsDir) => {
    if (!fs.existsSync(layoutsDir)) {
      return { overlay: null, sections: [], manifest: {}, layoutsDir };
    }
    const { manifest } = readLayoutManifest(layoutsDir);
    let overlay = null;
    if (manifest.overlay) {
      const p = path.join(layoutsDir, manifest.overlay);
      if (fs.existsSync(p)) overlay = { name: manifest.overlay, path: p };
    }
    if (!overlay) {
      for (const candidate of ['Overlay.png', 'overlay.png', 'pg6.png']) {
        const p = path.join(layoutsDir, candidate);
        if (fs.existsSync(p)) {
          overlay = { name: candidate, path: p };
          break;
        }
      }
    }
    const sections = [];
    const sectionMap = manifest.sections || {};
    const zoneKeys = Object.keys(sectionMap).sort((a, b) => Number(a) - Number(b));
    if (zoneKeys.length) {
      zoneKeys.forEach((zone) => {
        const name = sectionMap[zone];
        const p = path.join(layoutsDir, name);
        if (fs.existsSync(p)) {
          sections.push({ zone: Number(zone), name, path: p });
        }
      });
    } else {
      fs.readdirSync(layoutsDir)
        .filter((n) => /\.(png|jpg|jpeg|pdf)$/i.test(n))
        .sort()
        .forEach((name) => {
          const stem = path.parse(name).name.toLowerCase();
          if (stem === 'overlay' || stem === 'pg6') return;
          const m = stem.match(/^section[_-]?0?(\d+)$/i);
          if (m) {
            sections.push({
              zone: Number(m[1]),
              name,
              path: path.join(layoutsDir, name),
            });
          }
        });
      sections.sort((a, b) => a.zone - b.zone);
    }
    return { overlay, sections, manifest, layoutsDir };
  };

  ipcMain.handle('load-layout-files', async (event, data) => {
    try {
      const { system } = data || {};
      const root = path.join(__dirname, '..');
      const layoutsDir = layoutsDirForSystem(root, system);
      const listing = listLayoutFolder(layoutsDir);
      return { success: true, ...listing };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('save-layout-files', async (event, data) => {
    try {
      const { system, overlayPath, sectionPaths, clearSections } = data || {};
      const sys = sanitizeSystemName(system);
      const root = path.join(__dirname, '..');
      const layoutsDir = layoutsDirForSystem(root, sys);
      fs.mkdirSync(layoutsDir, { recursive: true });

      const { manifest, manifestPath } = readLayoutManifest(layoutsDir);
      if (!manifest.sections) manifest.sections = {};

      if (overlayPath && fs.existsSync(overlayPath)) {
        const ext = path.extname(overlayPath) || '.png';
        const destName = `Overlay${ext}`;
        fs.copyFileSync(overlayPath, path.join(layoutsDir, destName));
        manifest.overlay = destName;
      }

      if (clearSections) {
        manifest.sections = {};
      }

      const incoming = Array.isArray(sectionPaths) ? sectionPaths.filter((p) => p && fs.existsSync(p)) : [];
      if (incoming.length) {
        const usedZones = Object.keys(manifest.sections).map((z) => Number(z)).filter((n) => !Number.isNaN(n));
        let nextZone = usedZones.length ? Math.max(...usedZones) + 1 : 1;
        incoming.forEach((src) => {
          const ext = path.extname(src) || '.png';
          const destName = `Section_${String(nextZone).padStart(2, '0')}${ext}`;
          fs.copyFileSync(src, path.join(layoutsDir, destName));
          manifest.sections[String(nextZone)] = destName;
          nextZone += 1;
        });
      }

      // Drawing OCR prefix follows target system (SITE_MCP05 → SITE), not a fixed facility name.
      if (!manifest.site_code && sys && sys !== 'project') {
        manifest.site_code = sys.split('_')[0].toUpperCase();
      }

      writeLayoutManifest(manifestPath, manifest);
      const listing = listLayoutFolder(layoutsDir);
      return {
        success: true,
        layoutsDir,
        manifest,
        overlay: listing.overlay,
        sections: listing.sections,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Failed to save layout files.' };
    }
  });

  ipcMain.handle('select-layout-files', async (event, data) => {
    try {
      const { mode, defaultDir } = data || {};
      const isOverlay = mode === 'overlay';
      const result = await dialog.showOpenDialog({
        properties: isOverlay ? ['openFile'] : ['openFile', 'multiSelections'],
        title: isOverlay ? 'Select project overlay (full machine)' : 'Select machine section drawings',
        defaultPath: defaultDir && fs.existsSync(defaultDir) ? defaultDir : undefined,
        filters: [
          { name: 'Images & PDF', extensions: ['png', 'jpg', 'jpeg', 'pdf'] },
          { name: 'PNG', extensions: ['png'] },
          { name: 'PDF', extensions: ['pdf'] },
          { name: 'All Files (*.*)', extensions: ['*'] },
        ],
      });
      if (result.canceled || !result.filePaths.length) {
        return { success: false, paths: [] };
      }
      return { success: true, paths: result.filePaths };
    } catch (err) {
      return { success: false, message: err.message, paths: [] };
    }
  });

  ipcMain.handle('build-spatial-layout', async (event, data) => {
    try {
      const { system } = data || {};
      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return { success: false, message: 'Python not found. Run Launch-ProjectIntake.bat.' };
      }

      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const layoutsDir = layoutsDirForSystem(root, sys);
      if (!fs.existsSync(layoutsDir)) {
        return {
          success: false,
          message: `No layouts folder found. Drop overlay + section files first.\nExpected: ${layoutsDir}`,
        };
      }

      const listing = listLayoutFolder(layoutsDir);
      if (!listing.overlay) {
        return {
          success: false,
          message: 'No overlay found. Drop Overlay.png (full machine with zones 1–5) first.',
        };
      }

      const scriptPath = path.join(root, 'tools', 'scripts', 'build_spatial_layout.py');
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
      archiveIntakePhaseIfExists(siteDir, 'spatial');
      const outDir = intakeExportDir(siteDir, 'spatial');
      fs.mkdirSync(outDir, { recursive: true });

      const scaffoldCsv = path.join(intakeExportDir(siteDir, 'rough-program'), 'scaffold_tags.csv');
      const args = [
        scriptPath,
        layoutsDir,
        '--system', sys,
        '--out-dir', outDir,
      ];
      if (fs.existsSync(scaffoldCsv)) {
        args.push('--scaffold-csv', scaffoldCsv);
      }

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({ code: -1, stdout, stderr: [stderr, err?.message].filter(Boolean).join('\n') });
        });
        child.on('close', (code) => resolve({ code, stdout, stderr }));
      });

      const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
      const spatialPath = path.join(outDir, 'spatial_layout.json');
      if (runResult.code !== 0 || !fs.existsSync(spatialPath)) {
        let failMsg = `Spatial layout build failed (exit ${runResult.code}).`;
        if (pyLog.includes('easyocr') || pyLog.includes('No module named')) {
          failMsg += '\nInstall OCR: pip install easyocr opencv-python-headless';
        } else if (pyLog.trim()) {
          failMsg += `\n\n${pyLog.trim().slice(0, 1200)}`;
        }
        return { success: false, message: failMsg, log: pyLog };
      }

      const spatial = JSON.parse(fs.readFileSync(spatialPath, 'utf8'));
      return {
        success: true,
        spatial,
        spatialPath,
        outputDir: outDir,
        projectFolder: siteDir,
        relativePath: intakeRelativePath(siteFolder, 'exports/spatial'),
        log: pyLog,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Spatial layout build failed.' };
    }
  });

  ipcMain.handle('open-system-folder', async (event, data) => {
    try {
      const { system, folder } = data || {};
      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const { siteDir } = ensureIntakeSiteDir(sys);
      const subfolders = {
        project: siteDir,
        exports: path.join(siteDir, 'exports'),
        layouts: path.join(siteDir, 'layouts'),
        acade: intakeExportDir(siteDir, 'acade-io'),
        scaffold: intakeExportDir(siteDir, 'rough-program'),
        spatial: intakeExportDir(siteDir, 'spatial'),
        emulation: intakeExportDir(siteDir, 'emulation'),
        allSites: intakeOutputRoot(),
        archive: path.join(siteDir, 'archive'),
      };
      const dir = subfolders[folder] || subfolders.exports;
      fs.mkdirSync(dir, { recursive: true });
      const err = await shell.openPath(dir);
      if (err) return { success: false, message: err, path: dir };
      return { success: true, path: dir };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('open-path', async (event, targetPath) => {
    try {
      if (!targetPath) return { success: false, message: 'No path provided.' };
      const resolved = path.resolve(targetPath);
      if (!fs.existsSync(resolved)) {
        return { success: false, message: `Path not found: ${resolved}` };
      }
      const stat = fs.statSync(resolved);
      if (stat.isDirectory()) {
        const err = await shell.openPath(resolved);
        if (err) return { success: false, message: err };
      } else {
        shell.showItemInFolder(resolved);
      }
      return { success: true, path: resolved };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  const knowledgeCorpusRoot = () => path.join(__dirname, '..', 'knowledge-corpus');
  const prismVectorScript = () => path.join(__dirname, '..', 'Rockwell-Vector-Database.py');
  const prismVectorReq = () => path.join(__dirname, '..', 'rockwell-vector-db', 'requirements.txt');

  function runPrismVectorCli(args) {
    const pythonExe = findPythonExecutable();
    if (!pythonExe) {
      return { success: false, message: 'Python not found. Install from https://python.org' };
    }
    const root = path.join(__dirname, '..');
    const script = prismVectorScript();
    if (!fs.existsSync(script)) {
      return { success: false, message: 'Rockwell-Vector-Database.py not found.' };
    }
    const req = prismVectorReq();
    if (fs.existsSync(req)) {
      spawnSync(pythonExe, ['-m', 'pip', 'install', '-q', '-r', req], {
        encoding: 'utf8',
        cwd: root,
        shell: process.platform === 'win32',
        windowsHide: true,
      });
    }
    const result = spawnSync(pythonExe, [script, ...args], {
      encoding: 'utf8',
      cwd: root,
      shell: process.platform === 'win32',
      windowsHide: true,
      maxBuffer: 20 * 1024 * 1024,
    });
    const stdout = (result.stdout || '').trim();
    const stderr = (result.stderr || '').trim();
    if (result.status !== 0) {
      return {
        success: false,
        message: stderr || stdout || `Vector CLI exited with code ${result.status}`,
        log: stderr,
      };
    }
    let data = null;
    if (stdout.startsWith('{') || stdout.startsWith('[')) {
      try { data = JSON.parse(stdout); } catch (_) { /* plain text */ }
    }
    return { success: true, data, stdout, stderr };
  }

  const prismSiteSubfolders = () => ['programs', 'io', 'prints', 'layouts', 'hmi', 'generated'];

  function ensurePrismSiteDirs(siteName) {
    const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(siteName));
    const siteRoot = path.join(knowledgeCorpusRoot(), siteFolder);
    prismSiteSubfolders().forEach((sub) => {
      fs.mkdirSync(path.join(siteRoot, sub), { recursive: true });
    });
    return { siteFolder, siteRoot, relativePath: `knowledge-corpus/${siteFolder}` };
  }

  const prismCorpusSiteSkip = new Set(['docs']);

  ipcMain.handle('prism-list-sites', async () => {
    try {
      const root = knowledgeCorpusRoot();
      fs.mkdirSync(root, { recursive: true });
      const sites = fs.readdirSync(root)
        .filter((name) => {
          if (name.startsWith('.') || prismCorpusSiteSkip.has(name.toLowerCase())) return false;
          const full = path.join(root, name);
          try {
            return fs.statSync(full).isDirectory();
          } catch (_) {
            return false;
          }
        })
        .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
      return { success: true, sites, root };
    } catch (err) {
      return { success: false, message: err.message, sites: [] };
    }
  });

  ipcMain.handle('prism-create-site', async (event, data) => {
    try {
      const { siteName } = data || {};
      const raw = String(siteName || '').trim();
      if (!raw) {
        return { success: false, message: 'Enter a site name (e.g. SITE_MCP06).' };
      }
      const { siteFolder, siteRoot, relativePath } = ensurePrismSiteDirs(raw);
      return {
        success: true,
        site: siteFolder,
        path: siteRoot,
        relativePath,
        message: `Created ${relativePath}/ with programs, io, prints, layouts, hmi, generated`,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('prism-delete-site', async (event, data) => {
    try {
      const raw = String((data && data.site) || '').trim();
      if (!raw) {
        return { success: false, message: 'Select a site to remove.' };
      }
      const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(raw));
      if (prismCorpusSiteSkip.has(siteFolder.toLowerCase())) {
        return { success: false, message: `Cannot remove reserved folder: ${siteFolder}` };
      }
      const siteRoot = path.join(knowledgeCorpusRoot(), siteFolder);
      if (!fs.existsSync(siteRoot)) {
        return {
          success: true,
          site: siteFolder,
          message: `Site folder already gone: knowledge-corpus/${siteFolder}/`,
        };
      }
      const resolved = path.resolve(siteRoot);
      const corpusResolved = path.resolve(knowledgeCorpusRoot());
      if (!resolved.startsWith(corpusResolved + path.sep) && resolved !== corpusResolved) {
        return { success: false, message: 'Refusing to delete path outside knowledge-corpus.' };
      }
      fs.rmSync(resolved, { recursive: true, force: true });
      return {
        success: true,
        site: siteFolder,
        message: `Removed knowledge-corpus/${siteFolder}/ — click Rebuild Index to refresh search.`,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('prism-select-files', async (event, data) => {
    try {
      const { extensions, multiple } = data || {};
      const extList = String(extensions || '')
        .split(',')
        .map((e) => e.trim().replace(/^\./, '').toLowerCase())
        .filter(Boolean);
      const filters = extList.length
        ? [
          { name: 'Corpus files', extensions: extList },
          { name: 'All files', extensions: ['*'] },
        ]
        : [{ name: 'All files', extensions: ['*'] }];
      const result = await dialog.showOpenDialog({
        properties: multiple === false ? ['openFile'] : ['openFile', 'multiSelections'],
        title: 'Select files for PRISM corpus',
        filters,
      });
      if (result.canceled || !result.filePaths.length) {
        return { success: false, files: [] };
      }
      return {
        success: true,
        files: result.filePaths.map((fp) => ({
          path: fp,
          name: path.basename(fp),
        })),
      };
    } catch (err) {
      return { success: false, message: err.message, files: [] };
    }
  });

  ipcMain.handle('prism-stage-file', async (event, data) => {
    try {
      const { site, category, fileName, content, sourcePath } = data || {};
      const cat = (category || 'programs').toLowerCase();
      let dest;
      let relativePath;
      let siteFolder = '';

      if (cat === 'docs') {
        const docsDir = path.join(knowledgeCorpusRoot(), 'docs');
        fs.mkdirSync(docsDir, { recursive: true });
        const safeName = path.basename(fileName || sourcePath || 'upload.md');
        dest = path.join(docsDir, safeName);
        relativePath = `knowledge-corpus/docs/${safeName}`;
      } else {
        const rawSite = String(site || '').trim();
        if (!rawSite) {
          return { success: false, message: 'Select or create a site before staging files.' };
        }
        const ensured = ensurePrismSiteDirs(rawSite);
        siteFolder = ensured.siteFolder;
        const allowed = new Set(['programs', 'io', 'prints', 'layouts', 'hmi']);
        const folder = allowed.has(cat) ? cat : 'programs';
        const siteDir = path.join(ensured.siteRoot, folder);
        fs.mkdirSync(siteDir, { recursive: true });
        const safeName = path.basename(fileName || sourcePath || 'upload.dat');
        dest = path.join(siteDir, safeName);
        relativePath = `knowledge-corpus/${siteFolder}/${folder}/${safeName}`;
      }

      let action = 'copy';
      if (sourcePath && fs.existsSync(sourcePath)) {
        if (fs.existsSync(dest)) {
          const srcMtime = fs.statSync(sourcePath).mtimeMs;
          const destMtime = fs.statSync(dest).mtimeMs;
          if (srcMtime <= destMtime) {
            return {
              success: true,
              action: 'skip_older',
              path: dest,
              relativePath,
              site: siteFolder,
              category: cat,
              message: 'Corpus already has a newer copy — kept existing file.',
            };
          }
          action = 'replace';
        }
        fs.copyFileSync(sourcePath, dest);
      } else if (content != null) {
        fs.writeFileSync(dest, content, 'utf8');
      } else {
        return { success: false, message: 'Missing file path or content.' };
      }
      return {
        success: true,
        action,
        path: dest,
        relativePath,
        site: siteFolder,
        category: cat,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('prism-stats', async () => {
    const res = runPrismVectorCli(['stats']);
    if (!res.success) return res;
    return { success: true, ...(res.data || {}) };
  });

  ipcMain.handle('prism-index', async (event, data) => {
    const reset = !!(data && data.reset);
    const args = reset ? ['index', '--reset'] : ['index'];
    const res = runPrismVectorCli(args);
    if (!res.success) return res;
    return { success: true, ...(res.data || {}), message: res.data?.message || 'Index complete.' };
  });

  ipcMain.handle('prism-search', async (event, data) => {
    const { query, limit, system } = data || {};
    if (!query || !String(query).trim()) {
      return { success: false, message: 'Enter a search query.' };
    }
    const args = ['search', String(query).trim(), '--json', '--limit', String(limit || 10)];
    if (system) args.push('--system', String(system));
    const res = runPrismVectorCli(args);
    if (!res.success) return res;
    return { success: true, hits: res.data || [] };
  });

  ipcMain.handle('prism-context', async (event, data) => {
    const { query, notes, limit, system } = data || {};
    if (!query || !String(query).trim()) {
      return { success: false, message: 'Enter a build task description.' };
    }
    const args = ['context', String(query).trim(), '--json', '--limit', String(limit || 8)];
    if (system) args.push('--system', String(system));
    if (notes) args.push('--notes', String(notes));
    const res = runPrismVectorCli(args);
    if (!res.success) return res;
    return { success: true, bundle: res.data || {} };
  });

  ipcMain.handle('prism-save-output', async (event, data) => {
    try {
      const { site, fileName, content } = data || {};
      if (!content) return { success: false, message: 'No content to save.' };
      const siteFolder = sanitizeDemoFolderName(sanitizeSystemName(site || 'output'));
      const outDir = path.join(knowledgeCorpusRoot(), siteFolder, 'generated');
      fs.mkdirSync(outDir, { recursive: true });
      const name = path.basename(fileName || `prism_output_${Date.now()}.xml`);
      const outPath = path.join(outDir, name);
      fs.writeFileSync(outPath, content, 'utf8');
      return {
        success: true,
        path: outPath,
        relativePath: `knowledge-corpus/${siteFolder}/generated/${name}`,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('prism-open-corpus', async (event, data) => {
    try {
      const { site } = data || {};
      const base = knowledgeCorpusRoot();
      fs.mkdirSync(base, { recursive: true });
      const target = site
        ? path.join(base, sanitizeDemoFolderName(sanitizeSystemName(site)))
        : base;
      fs.mkdirSync(target, { recursive: true });
      const err = await shell.openPath(target);
      if (err) return { success: false, message: err };
      return { success: true, path: target };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('get-intake-health', async (event, data) => {
    try {
      const { system } = data || {};
      const sys = sanitizeSystemName(system);
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
      const exists = (p) => fs.existsSync(p);
      const acadeDir = path.join(siteDir, 'exports', 'acade-io');
      const scaffoldDir = path.join(siteDir, 'exports', 'rough-program');
      const spatialDir = path.join(siteDir, 'exports', 'spatial');
      const layoutsDir = path.join(siteDir, 'layouts');
      const emulationDir = path.join(siteDir, 'exports', 'emulation');
      return {
        success: true,
        system: sys,
        projectFolder: siteDir,
        relativePath: intakeRelativePath(siteFolder),
        hasImport: exists(path.join(acadeDir, 'summary.json')),
        hasScaffold: exists(path.join(scaffoldDir, 'scaffold_manifest.json')),
        hasSpatial: exists(path.join(spatialDir, 'spatial_layout.json')),
        hasLayouts: exists(layoutsDir) && fs.readdirSync(layoutsDir).some((n) => /\.(png|pdf|json)$/i.test(n)),
        hasEmulation: exists(emulationDir) && fs.readdirSync(emulationDir).some((n) => /\.(FACTORYIO|csv|json)$/i.test(n)),
        paths: { projectFolder: siteDir, acadeDir, scaffoldDir, spatialDir, layoutsDir, emulationDir },
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('load-spatial-cache', async (event, data) => {
    try {
      const { system } = data || {};
      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const { siteDir } = ensureIntakeSiteDir(sys);
      const spatialPath = path.join(siteDir, 'exports', 'spatial', 'spatial_layout.json');
      const legacySpatialPath = path.join(root, 'systems', sys, 'exports', 'spatial', 'spatial_layout.json');
      const resolvedSpatialPath = fs.existsSync(spatialPath) ? spatialPath : legacySpatialPath;
      const layoutsDir = layoutsDirForSystem(root, sys);
      const listing = listLayoutFolder(layoutsDir);
      if (!fs.existsSync(resolvedSpatialPath)) {
        return {
          success: true,
          hasSpatial: false,
          layouts: listing,
        };
      }
      const spatial = JSON.parse(fs.readFileSync(resolvedSpatialPath, 'utf8'));
      return {
        success: true,
        hasSpatial: true,
        spatial,
        spatialPath: resolvedSpatialPath,
        outputDir: path.dirname(resolvedSpatialPath),
        projectFolder: siteDir,
        layouts: listing,
      };
    } catch (err) {
      return { success: false, message: err.message };
    }
  });

  ipcMain.handle('generate-factory-io-scene', async (event, data) => {
    try {
      const { system, area, scaffoldDir, mode } = data || {};
      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return { success: false, message: 'Python not found. Run Launch-ProjectIntake.bat.' };
      }

      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const exportMode = mode === 'io-map' ? 'io-map' : 'fat';
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
      const siteScaffoldDir = intakeExportDir(siteDir, 'rough-program');
      const legacyScaffoldDir = path.join(root, LEGACY_INTAKE_ROOT, sys, 'exports', 'rough-program');
      const systemsScaffoldDir = path.join(root, 'systems', sys, 'exports', 'rough-program');
      const resolvedScaffoldDir = (scaffoldDir && fs.existsSync(scaffoldDir))
        ? scaffoldDir
        : (fs.existsSync(path.join(siteScaffoldDir, 'factory_io_bindings.csv'))
          ? siteScaffoldDir
          : (fs.existsSync(path.join(legacyScaffoldDir, 'factory_io_bindings.csv'))
            ? legacyScaffoldDir
            : systemsScaffoldDir));
      const bindingsPath = path.join(resolvedScaffoldDir, 'factory_io_bindings.csv');
      if (!fs.existsSync(bindingsPath)) {
        return {
          success: false,
          message: `No factory_io_bindings.csv found. Generate scaffold first.\nExpected: ${bindingsPath}`,
        };
      }

      const areaName = exportMode === 'io-map'
        ? ''
        : (resolveScaffoldFioArea(resolvedScaffoldDir, area) || sys);
      if (exportMode === 'fat' && !areaName) {
        return {
          success: false,
          message: 'Could not determine scaffold area for Factory I/O scene. Re-run Generate Scaffold.',
        };
      }

      archiveIntakePhaseIfExists(siteDir, 'emulation');
      const outputDir = intakeExportDir(siteDir, 'emulation');
      fs.mkdirSync(outputDir, { recursive: true });

      const scriptPath = path.join(root, 'tools', 'scripts', 'generate_factory_io_scene.py');
      const args = [
        scriptPath,
        bindingsPath,
        '--area', areaName || sys,
        '--system', sys,
        '--out-dir', outputDir,
        '--mode', exportMode,
      ];

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({ code: -1, stdout, stderr: [stderr, err?.message].filter(Boolean).join('\n') });
        });
        child.on('close', (code) => resolve({ code, stdout, stderr }));
      });

      const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
      const sceneBaseName = exportMode === 'io-map' ? `${sys}_IO_MAP` : areaName;
      const sceneFile = path.join(outputDir, `${sceneBaseName}.FACTORYIO`);
      const manifestPath = path.join(outputDir, 'fio_scene_manifest.json');
      if (runResult.code !== 0 || !fs.existsSync(sceneFile)) {
        return {
          success: false,
          message: `Factory I/O scene export failed (exit ${runResult.code}).`,
          log: pyLog,
        };
      }

      let manifest = null;
      if (fs.existsSync(manifestPath)) {
        manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      }

      const scenePath = path.join(outputDir, `${sceneBaseName}.FACTORYIO`);
      return {
        success: true,
        outputDir,
        sceneFile: `${sceneBaseName}.FACTORYIO`,
        scenePath,
        exportMode,
        driverBindingsPath: path.join(outputDir, 'fio_driver_bindings.csv'),
        relativePath: intakeRelativePath(siteFolder, `exports/emulation/${sceneBaseName}.FACTORYIO`),
        photoeyeCount: manifest?.stats?.photoeyes_placed || manifest?.stats?.inputs_mapped || 0,
        ioTagCount: manifest?.stats?.total_tags || 0,
        setupSteps: manifest?.setup_steps || [],
        log: pyLog,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Factory I/O scene export failed.' };
    }
  });

  function resolveIntakeScaffoldDir(sys, scaffoldDir) {
    const root = path.join(__dirname, '..');
    const { siteDir } = ensureIntakeSiteDir(sys);
    const siteScaffoldDir = intakeExportDir(siteDir, 'rough-program');
    const legacyScaffoldDir = path.join(root, LEGACY_INTAKE_ROOT, sys, 'exports', 'rough-program');
    const systemsScaffoldDir = path.join(root, 'systems', sys, 'exports', 'rough-program');
    if (scaffoldDir && fs.existsSync(scaffoldDir)) return scaffoldDir;
    if (fs.existsSync(path.join(siteScaffoldDir, 'factory_io_bindings.csv'))) return siteScaffoldDir;
    if (fs.existsSync(path.join(legacyScaffoldDir, 'factory_io_bindings.csv'))) return legacyScaffoldDir;
    return systemsScaffoldDir;
  }

  function findEmulate3dExecutable() {
    const candidates = [
      path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Emulate3D Ltd', 'Emulate3D', 'Emulate3D.exe'),
      path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Emulate3D', 'Emulate3D.exe'),
      path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Emulate3D Ltd', 'Emulate3D', 'Emulate3D.exe'),
      path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Rockwell Automation', 'Emulate3D', 'Emulate3D.exe'),
    ];
    for (const p of candidates) {
      if (fs.existsSync(p)) return p;
    }
    return null;
  }

  async function runEmulate3dSceneExport({ system, area, scaffoldDir, mode }) {
    const pythonExe = findPythonExecutable();
    if (!pythonExe) {
      return { success: false, message: 'Python not found. Run Launch-ProjectIntake.bat.' };
    }

    const root = path.join(__dirname, '..');
    const sys = sanitizeSystemName(system);
    const exportMode = mode === 'io-map' ? 'io-map' : (mode === 'full' ? 'full' : 'fat');
    const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
    const resolvedScaffoldDir = resolveIntakeScaffoldDir(sys, scaffoldDir);
    const bindingsPath = path.join(resolvedScaffoldDir, 'factory_io_bindings.csv');
    if (!fs.existsSync(bindingsPath)) {
      return {
        success: false,
        message: `No factory_io_bindings.csv found. Generate scaffold first.\nExpected: ${bindingsPath}`,
      };
    }

    const areaName = exportMode === 'io-map'
      ? ''
      : (resolveScaffoldFioArea(resolvedScaffoldDir, area) || '');

    archiveIntakePhaseIfExists(siteDir, 'emulation');
    const outputDir = intakeExportDir(siteDir, 'emulation');
    fs.mkdirSync(outputDir, { recursive: true });

    const scriptPath = path.join(root, 'tools', 'scripts', 'generate_emulate3d_scene.py');
    const args = [
      scriptPath,
      bindingsPath,
      '--system', sys,
      '--out-dir', outputDir,
      '--mode', exportMode,
    ];
    if (areaName) args.push('--area', areaName);

    const runResult = await new Promise((resolve) => {
      const child = spawnPython(pythonExe, args, buildPythonEnv());
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
      child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
      child.on('error', (err) => {
        resolve({ code: -1, stdout, stderr: [stderr, err?.message].filter(Boolean).join('\n') });
      });
      child.on('close', (code) => resolve({ code, stdout, stderr }));
    });

    const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
    const manifestPath = path.join(outputDir, 'e3d_scene_manifest.json');
    const bindingsCsv = path.join(outputDir, 'emulate3d_tag_bindings.csv');
    if (runResult.code !== 0 || !fs.existsSync(bindingsCsv)) {
      return {
        success: false,
        message: `Emulate3D export failed (exit ${runResult.code}).`,
        log: pyLog,
      };
    }

    let manifest = null;
    if (fs.existsSync(manifestPath)) {
      manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    }

    const blueprintFile = manifest?.blueprint_file || `e3d_scene_blueprint_${areaName}.json`;
    return {
      success: true,
      outputDir,
      exportMode,
      bindingsFile: 'emulate3d_tag_bindings.csv',
      bindingsPath: bindingsCsv,
      blueprintFile,
      blueprintPath: path.join(outputDir, blueprintFile),
      driverMapFile: 'e3d_logix_driver_map.csv',
      checklistFile: 'e3d_first_run_checklist.txt',
      relativePath: intakeRelativePath(siteFolder, 'exports/emulation/emulate3d_tag_bindings.csv'),
      simObjectCount: manifest?.stats?.blueprint_objects || manifest?.stats?.sim_objects || 0,
      photoeyeCount: manifest?.stats?.photoeyes || 0,
      ioTagCount: manifest?.stats?.bindings_exported || 0,
      setupSteps: manifest?.setup_steps || [],
      emulate3dPath: findEmulate3dExecutable(),
      log: pyLog,
    };
  }

  ipcMain.handle('generate-emulate3d-bindings', async (event, data) => {
    try {
      return await runEmulate3dSceneExport({ ...data, mode: 'fat' });
    } catch (err) {
      return { success: false, message: err.message || 'Emulate3D bindings export failed.' };
    }
  });

  ipcMain.handle('generate-emulate3d-scene', async (event, data) => {
    try {
      return await runEmulate3dSceneExport(data || {});
    } catch (err) {
      return { success: false, message: err.message || 'Emulate3D scene export failed.' };
    }
  });

  ipcMain.handle('detect-emulate3d', async () => {
    const exe = findEmulate3dExecutable();
    return {
      installed: !!exe,
      path: exe || null,
      bridgeScript: path.join(__dirname, '..', 'tools', 'emulate3d-bridge', 'Launch-E3dBridge.ps1'),
    };
  });

  ipcMain.handle('launch-emulate3d-bridge', async (event, data) => {
    try {
      const { system, openApp, regenerate } = data || {};
      const sys = sanitizeSystemName(system || 'MGE9_MCP05');
      const root = path.join(__dirname, '..');
      const bridgePs1 = path.join(root, 'tools', 'emulate3d-bridge', 'Launch-E3dBridge.ps1');
      if (!fs.existsSync(bridgePs1)) {
        return { success: false, message: `Bridge script not found: ${bridgePs1}` };
      }
      const scaffoldDir = resolveIntakeScaffoldDir(sys, '');
      const emulationArea = resolveScaffoldFioArea(scaffoldDir, data?.area || '');
      const args = ['-ExecutionPolicy', 'Bypass', '-File', bridgePs1, '-System', sys];
      if (openApp) args.push('-OpenEmulate3D');
      if (regenerate) args.push('-Regenerate');
      if (emulationArea) args.push('-Scene', emulationArea);

      return await new Promise((resolve) => {
        const child = spawn('powershell.exe', args, {
          cwd: root,
          windowsHide: false,
          shell: false,
        });
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({ success: false, message: err.message || 'Failed to launch Emulate3D bridge.' });
        });
        child.on('close', (code) => {
          const pyLog = [stdout, stderr].filter(Boolean).join('\n');
          if (code === 0) {
            resolve({
              success: true,
              message: 'Emulate3D bridge launched - emulation folder opened.',
              emulate3dPath: findEmulate3dExecutable(),
              area: emulationArea || null,
              log: pyLog,
            });
          } else {
            resolve({
              success: false,
              message: `Emulate3D bridge exited with code ${code}.`,
              log: pyLog,
            });
          }
        });
      });
    } catch (err) {
      return { success: false, message: err.message || 'Emulate3D bridge failed.' };
    }
  });

  ipcMain.handle('extract-layout-from-dxf', async (event, data) => {
    try {
      const { system, dxfFolder, scaffoldDir } = data || {};
      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return { success: false, message: 'Python not found. Run Launch-ProjectIntake.bat.' };
      }

      const root = path.join(__dirname, '..');
      const sys = sanitizeSystemName(system);
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);

      let resolvedDxf = (dxfFolder || '').trim();
      if (!resolvedDxf || !fs.existsSync(resolvedDxf)) {
        const candidates = [
          path.join(siteDir, 'layouts', 'dxf'),
          path.join(siteDir, 'exports', 'layouts', 'dxf'),
          path.join(root, 'systems', sys, 'layouts', 'dxf'),
        ];
        resolvedDxf = candidates.find((p) => fs.existsSync(p) && fs.readdirSync(p).some((n) => /\.dxf$/i.test(n))) || '';
      }
      if (!resolvedDxf) {
        return {
          success: false,
          message: 'No DXF folder found. Drop .dxf files in layouts/dxf under your project folder, or pass dxfFolder.',
        };
      }

      const siteScaffoldDir = intakeExportDir(siteDir, 'rough-program');
      const legacyScaffoldDir = path.join(root, LEGACY_INTAKE_ROOT, sys, 'exports', 'rough-program');
      const systemsScaffoldDir = path.join(root, 'systems', sys, 'exports', 'rough-program');
      const resolvedScaffoldDir = (scaffoldDir && fs.existsSync(scaffoldDir))
        ? scaffoldDir
        : (fs.existsSync(path.join(siteScaffoldDir, 'scaffold_tags.csv'))
          ? siteScaffoldDir
          : (fs.existsSync(path.join(legacyScaffoldDir, 'scaffold_tags.csv'))
            ? legacyScaffoldDir
            : systemsScaffoldDir));
      const scaffoldCsv = path.join(resolvedScaffoldDir, 'scaffold_tags.csv');

      archiveIntakePhaseIfExists(siteDir, 'spatial');
      const outDir = intakeExportDir(siteDir, 'spatial');
      fs.mkdirSync(outDir, { recursive: true });

      const scriptPath = path.join(root, 'tools', 'scripts', 'extract_layout_from_dxf.py');
      const args = [
        scriptPath,
        resolvedDxf,
        '--system', sys,
        '--out-dir', outDir,
      ];
      if (fs.existsSync(scaffoldCsv)) {
        args.push('--scaffold-csv', scaffoldCsv);
      }

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({ code: -1, stdout, stderr: [stderr, err?.message].filter(Boolean).join('\n') });
        });
        child.on('close', (code) => resolve({ code, stdout, stderr }));
      });

      const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
      const layoutPath = path.join(outDir, 'machine_layout.json');
      if (runResult.code !== 0 || !fs.existsSync(layoutPath)) {
        return {
          success: false,
          message: `DXF layout extract failed (exit ${runResult.code}).`,
          log: pyLog,
        };
      }

      let manifest = null;
      try {
        manifest = JSON.parse(fs.readFileSync(layoutPath, 'utf8'));
      } catch (_) { /* ignore */ }

      return {
        success: true,
        outputDir: outDir,
        layoutPath,
        relativePath: intakeRelativePath(siteFolder, 'exports/spatial/machine_layout.json'),
        equipmentPoints: manifest?.stats?.equipment_points || 0,
        plcMatched: manifest?.stats?.plc_matched || 0,
        matchPct: manifest?.stats?.plc_match_pct || 0,
        log: pyLog,
      };
    } catch (err) {
      return { success: false, message: err.message || 'DXF layout extract failed.' };
    }
  });

  ipcMain.handle('generate-rough-program', async (event, data) => {
    try {
      const { summaryPath, system, outputDir: priorDir, l5xPath } = data || {};
      if (!summaryPath || !fs.existsSync(summaryPath)) {
        return {
          success: false,
          message: 'No import summary found. Run Import I/O first (Excel + L5X).',
        };
      }

      const pythonExe = findPythonExecutable();
      if (!pythonExe) {
        return {
          success: false,
          message: 'Python not found. Run Launch-ProjectIntake.bat.',
        };
      }

      const root = path.join(__dirname, '..');
      const scriptPath = path.join(root, 'tools', 'scripts', 'generate_rough_program.py');
      const sys = (system || 'project').replace(/[^A-Za-z0-9_-]/g, '_');
      const { siteDir, siteFolder } = ensureIntakeSiteDir(sys);
      archiveIntakePhaseIfExists(siteDir, 'rough-program');
      const outputDir = intakeExportDir(siteDir, 'rough-program');
      fs.mkdirSync(outputDir, { recursive: true });

      const manifestPath = path.join(outputDir, 'scaffold_manifest.json');
      const args = [
        scriptPath,
        summaryPath,
        '--system', sys,
        '--out-dir', outputDir,
        '--summary-json', manifestPath,
      ];
      if (l5xPath && fs.existsSync(l5xPath)) {
        args.push('--compare-l5x', path.resolve(l5xPath));
      }

      const runResult = await new Promise((resolve) => {
        const child = spawnPython(pythonExe, args, buildPythonEnv());
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (err) => {
          resolve({ code: -1, stdout, stderr: [stderr, err?.message].filter(Boolean).join('\n') });
        });
        child.on('close', (code) => resolve({ code, stdout, stderr }));
      });

      const pyLog = [runResult.stdout, runResult.stderr].filter(Boolean).join('\n');
      if (runResult.code !== 0 || !fs.existsSync(manifestPath)) {
        return {
          success: false,
          message: `Scaffold generation failed (exit ${runResult.code}).`,
          log: pyLog,
        };
      }

      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      const readIfExists = (name) => {
        const p = path.join(outputDir, name);
        return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
      };

      return {
        success: true,
        manifest,
        outputDir,
        projectFolder: siteDir,
        relativePath: intakeRelativePath(siteFolder, 'exports/rough-program'),
        priorImportDir: priorDir || null,
        l5xContent: readIfExists('scaffold.L5X'),
        tagsCsvContent: readIfExists('scaffold_tags.csv'),
        factoryIoCsvContent: readIfExists('factory_io_bindings.csv'),
        xmlContent: readIfExists('scaffold_program.xml'),
        l5xDiff: fs.existsSync(path.join(outputDir, 'l5x_diff.json'))
          ? JSON.parse(fs.readFileSync(path.join(outputDir, 'l5x_diff.json'), 'utf8'))
          : null,
        log: pyLog,
      };
    } catch (err) {
      return { success: false, message: err.message || 'Scaffold generation failed.' };
    }
  });

  // Inject ultra-cool custom titlebar after load (Rockwell Git dashboard only)
  win.webContents.on('did-finish-load', () => {
    if (IS_PROJECT_INTAKE || IS_PRISM) return;
    const titlebarHTML = `
      <div id="rockwell-titlebar" style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 44px;
        background: #0a0a0c;
        border-bottom: 1px solid #27272a;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 14px 0 18px;
        z-index: 999999;
        -webkit-app-region: drag;
        user-select: none;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
      ">
        <!-- Left: Premium Branding -->
        <div style="display: flex; align-items: center; gap: 13px; -webkit-app-region: drag;">
          <!-- Cool Industrial Logo -->
          <div style="
            position: relative;
            width: 28px; 
            height: 28px; 
            background: linear-gradient(135deg, #f97316 0%, #fb923c 100%);
            border-radius: 7px; 
            display: flex; 
            align-items: center; 
            justify-content: center;
            box-shadow: 0 0 0 1px #3f2a1f, 0 0 18px rgba(249, 115, 22, 0.45);
          ">
            <span style="
              color: #111113; 
              font-weight: 900; 
              font-size: 16px; 
              letter-spacing: -1.5px;
              text-shadow: 0 1px 1px rgba(0,0,0,0.2);
            ">RG</span>
            <div style="
              position: absolute;
              top: 3px; right: 3px;
              width: 6px; height: 6px;
              background: #111113;
              border-radius: 50%;
              opacity: 0.3;
            "></div>
          </div>

          <div>
            <div style="display: flex; align-items: baseline; gap: 1px;">
              <span style="color: #f4f4f5; font-weight: 700; font-size: 15px; letter-spacing: -0.4px;">ROCKWELL</span>
              <span style="color: #f97316; font-weight: 800; font-size: 15px; letter-spacing: -0.5px; margin-left: 1px;">GIT</span>
            </div>
            <div style="margin-top: -3px;">
              <span style="color: #52525b; font-size: 9px; font-weight: 600; letter-spacing: 1.5px;">PLC STUDIO</span>
            </div>
          </div>
        </div>

        <!-- Center: current master file / routine -->
        <div style="
          color: #71717a;
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.3px;
          display: flex;
          align-items: center;
          gap: 8px;
          -webkit-app-region: drag;
          padding: 4px 14px;
          background: #111113;
          border-radius: 999px;
          border: 1px solid #27272a;
          max-width: 52%;
        ">
          <div id="rockwell-titlebar-dot" style="width: 7px; height: 7px; background: #ef4444; border-radius: 50%; box-shadow: 0 0 8px #ef4444; flex-shrink: 0;"></div>
          <span id="rockwell-titlebar-file" style="color: #71717a; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">-- no file loaded --</span>
        </div>

        <!-- Right: Premium Window Controls -->
        <div style="display: flex; align-items: center; gap: 2px; -webkit-app-region: no-drag; margin-right: -4px;">
          <div onclick="window.electronAPI.minimize()" style="
            width: 38px; height: 34px; display: flex; align-items: center; justify-content: center;
            border-radius: 5px; color: #71717a; font-size: 15px; transition: all .12s ease;
            font-family: monospace;
          " onmouseover="this.style.background='#27272a'; this.style.color='#e4e4e7'" 
             onmouseout="this.style.background='transparent'; this.style.color='#71717a'">
            &#8212;
          </div>
          <div onclick="window.electronAPI.maximize()" style="
            width: 38px; height: 34px; display: flex; align-items: center; justify-content: center;
            border-radius: 5px; color: #71717a; font-size: 13px; transition: all .12s ease;
          " onmouseover="this.style.background='#27272a'; this.style.color='#e4e4e7'" 
             onmouseout="this.style.background='transparent'; this.style.color='#71717a'">
            &#9633;
          </div>
          <div onclick="window.electronAPI.close()" style="
            width: 38px; height: 34px; display: flex; align-items: center; justify-content: center;
            border-radius: 5px; color: #71717a; font-size: 17px; transition: all .12s ease; line-height: 1;
          " onmouseover="this.style.background='#ef4444'; this.style.color='white'" 
             onmouseout="this.style.background='transparent'; this.style.color='#71717a'">
            &#10005;
          </div>
        </div>
      </div>
    `;

    // Inject titlebar + adjust dashboard content
    win.webContents.executeJavaScript(`
      (function() {
        // Remove any existing titlebar
        const existing = document.getElementById('rockwell-titlebar');
        if (existing) existing.remove();

        // Inject the titlebar
        document.body.insertAdjacentHTML('afterbegin', \`${titlebarHTML}\`);

        // Add top padding so dashboard content isn't hidden under the custom titlebar
        const style = document.createElement('style');
        style.id = 'rockwell-titlebar-style';
        style.textContent = \`
          body { 
            padding-top: 44px !important; 
          }
          .max-w-\\[1280px\\] { 
            max-width: 100% !important; 
            padding-left: 12px !important;
            padding-right: 12px !important;
          }
        \`;
        document.head.appendChild(style);

        // Optional: subtle improvement to dashboard container
        setTimeout(() => {
          const main = document.querySelector('.max-w-\\[1280px\\]');
          if (main) main.style.paddingTop = '4px';
        }, 100);
      })();
    `).catch(() => {});
  });

  // Show window
  win.once('ready-to-show', () => {
    win.show();
  });

  // Optional devtools
  // win.webContents.openDevTools({ mode: 'detach' });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
