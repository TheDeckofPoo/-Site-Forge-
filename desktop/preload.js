const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('fortnaAPI', {
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  searchDocs: (q) => ipcRenderer.invoke('search-docs', q),
  getRecipes: () => ipcRenderer.invoke('get-recipes'),
  getDocIndex: () => ipcRenderer.invoke('get-doc-index'),
  reindexDocs: () => ipcRenderer.invoke('reindex-docs'),
  importRun: (path) => ipcRenderer.invoke('import-run', path),
  getWorkspace: () => ipcRenderer.invoke('get-workspace'),
  clearWorkspace: () => ipcRenderer.invoke('clear-workspace'),
  listConveyors: () => ipcRenderer.invoke('list-conveyors'),
  listDevices: (data) => ipcRenderer.invoke('list-devices', data),
  applyRecipe: (data) => ipcRenderer.invoke('apply-recipe', data),
  openPath: (p) => ipcRenderer.invoke('open-path', p),
  openPrintPage: (data) => ipcRenderer.invoke('open-print-page', data || {}),
  selectArchive: (opts) => ipcRenderer.invoke('select-archive', opts || {}),
  exportPlc: (data) => ipcRenderer.invoke('export-plc', data),
  getIoBanks: () => ipcRenderer.invoke('get-io-banks'),
  ocrPrints: (data) => ipcRenderer.invoke('ocr-prints', data),
  autogenInspectExcel: (data) => ipcRenderer.invoke('autogen-inspect-excel', data || {}),
  autogenGenerate: (data) => ipcRenderer.invoke('autogen-generate', data || {}),
  autogenPreviewRun: (data) => ipcRenderer.invoke('autogen-preview-run', data || {}),
  autogenWorkbookBuild: (data) => ipcRenderer.invoke('autogen-workbook-build', data || {}),
  autogenWorkbookSave: (data) => ipcRenderer.invoke('autogen-workbook-save', data || {}),
  autogenWorkbookLoad: () => ipcRenderer.invoke('autogen-workbook-load'),
  autogenDefaults: () => ipcRenderer.invoke('autogen-defaults'),
  autogenVerify: () => ipcRenderer.invoke('autogen-verify'),
  autogenSelectExcel: () => ipcRenderer.invoke('autogen-select-excel'),
  autogenSelectLibrary: () => ipcRenderer.invoke('autogen-select-library'),
  transportBuildPoc: (data) => ipcRenderer.invoke('transport-build-poc', data || {}),
  transportLatestMerges: (data) => ipcRenderer.invoke('transport-latest-merges', data || {}),
  transportApplyAutogen: (data) => ipcRenderer.invoke('transport-apply-autogen', data || {}),
  onAutogenProgress: (cb) => {
    const handler = (_e, data) => cb(data);
    ipcRenderer.on('autogen-progress', handler);
    return () => ipcRenderer.removeListener('autogen-progress', handler);
  },
  getOcrProgress: () => ipcRenderer.invoke('get-ocr-progress'),
  getLastOcr: () => ipcRenderer.invoke('get-last-ocr'),
  clearLastOcr: () => ipcRenderer.invoke('clear-last-ocr'),
  onOcrProgress: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('ocr-progress', handler);
    return () => ipcRenderer.removeListener('ocr-progress', handler);
  },
  selectPrints: () => ipcRenderer.invoke('select-prints'),
  ignitionBuildLayout: (data) => ipcRenderer.invoke('ignition-build-layout', data || {}),
  ignitionPackPerspective: (data) => ipcRenderer.invoke('ignition-pack-perspective', data || {}),
  getPathForFile: (file) => {
    try { return webUtils.getPathForFile(file); } catch (_) { return file?.path || ''; }
  },
});