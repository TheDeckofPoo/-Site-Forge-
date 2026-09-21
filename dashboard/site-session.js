/**
 * Current-site session firewall — isolates async GUI updates across Clear / Load / machine change.
 *
 * activeSiteSession = { archive_sha, machine, loadEpoch }
 * Capture session at async start; before applying to GUI, reject if !== active.
 */
(function (root) {
  'use strict';

  const IO_PIPELINE = Object.freeze({
    IDLE: 'IDLE',
    LOADING_ARCHIVE: 'LOADING_ARCHIVE',
    TOPOLOGY_READY: 'TOPOLOGY_READY',
    PARSING_CLAIMS: 'PARSING_CLAIMS',
    RESOLVING_CLAIMS: 'RESOLVING_CLAIMS',
    BUILDING_MODEL: 'BUILDING_MODEL',
    READY: 'READY',
    REVIEW_REQUIRED: 'REVIEW_REQUIRED',
    FAILED: 'FAILED',
  });

  const LOADING_PHASES = new Set([
    IO_PIPELINE.LOADING_ARCHIVE,
    IO_PIPELINE.TOPOLOGY_READY,
    IO_PIPELINE.PARSING_CLAIMS,
    IO_PIPELINE.RESOLVING_CLAIMS,
    IO_PIPELINE.BUILDING_MODEL,
  ]);

  let active = { archive_sha: '', machine: '', loadEpoch: 0 };
  let ioPipelinePhase = IO_PIPELINE.IDLE;
  let presentedBuildKeys = new Set();
  let lastPresentedBuildKey = '';
  let twinGapScope = '';

  function cloneSession(s) {
    return {
      archive_sha: String(s?.archive_sha || ''),
      machine: String(s?.machine || ''),
      loadEpoch: Number(s?.loadEpoch || 0) || 0,
    };
  }

  function getActiveSiteSession() {
    return cloneSession(active);
  }

  function sessionEquals(a, b) {
    if (!a || !b) return false;
    return String(a.archive_sha || '') === String(b.archive_sha || '')
      && String(a.machine || '') === String(b.machine || '')
      && Number(a.loadEpoch || 0) === Number(b.loadEpoch || 0);
  }

  function sessionKey(s) {
    const x = cloneSession(s);
    return `${x.archive_sha}|${x.machine}|${x.loadEpoch}`;
  }

  function _logDiscard(label, detail, logFn) {
    const msg = `Session firewall: discard ${label}${detail ? ` (${detail})` : ''}`;
    if (typeof logFn === 'function') {
      try { logFn(msg, 'warn'); return; } catch (_) { /* fall through */ }
    }
    try {
      if (typeof root.autogenLog === 'function') root.autogenLog(msg, 'warn');
      else if (typeof root.log === 'function') root.log(msg, 'warn');
      else if (typeof console !== 'undefined') console.warn(msg);
    } catch (_) { /* ignore */ }
  }

  /** New RUN load / machine change — bump loadEpoch (invalidates in-flight async). */
  function beginSiteSession({ archive_sha = '', machine = '', reason = '' } = {}) {
    active = {
      archive_sha: String(archive_sha || ''),
      machine: String(machine || ''),
      loadEpoch: (Number(active.loadEpoch) || 0) + 1,
    };
    presentedBuildKeys = new Set();
    lastPresentedBuildKey = '';
    twinGapScope = sessionKey(active);
    ioPipelinePhase = IO_PIPELINE.LOADING_ARCHIVE;
    return cloneSession(active);
  }

  /**
   * Fill archive_sha / machine after import succeeds without bumping loadEpoch.
   * Keeps in-flight work started under this load valid.
   */
  function bindSiteSessionIdentity({ archive_sha, machine } = {}) {
    if (archive_sha != null) active.archive_sha = String(archive_sha || '');
    if (machine != null) active.machine = String(machine || '');
    twinGapScope = sessionKey(active);
    return cloneSession(active);
  }

  /** Clear Project / hard boundary — bump epoch, drop identity. */
  function invalidateSiteSession({ reason = 'clear' } = {}) {
    active = {
      archive_sha: '',
      machine: '',
      loadEpoch: (Number(active.loadEpoch) || 0) + 1,
    };
    presentedBuildKeys = new Set();
    lastPresentedBuildKey = '';
    twinGapScope = '';
    ioPipelinePhase = IO_PIPELINE.IDLE;
    return cloneSession(active);
  }

  function tagWithSession(payload) {
    const out = (payload && typeof payload === 'object' && !Array.isArray(payload))
      ? Object.assign({}, payload)
      : {};
    out.session = getActiveSiteSession();
    return out;
  }

  /**
   * Gate GUI apply for an async result.
   * Callers must pass the session captured at async start: { session: sessionAtStart, ... }.
   */
  function acceptAsyncResult(result, { label = 'async', logFn } = {}) {
    const resultSession = result?.session || result?.siteSession || null;
    if (!resultSession) {
      _logDiscard(label, `missing session tag; active=${sessionKey(active)}`, logFn);
      return false;
    }
    if (!sessionEquals(resultSession, active)) {
      _logDiscard(
        label,
        `result=${sessionKey(resultSession)} active=${sessionKey(active)}`,
        logFn,
      );
      return false;
    }
    return true;
  }

  function getIoPipelinePhase() {
    return ioPipelinePhase;
  }

  function setIoPipelinePhase(phase) {
    const p = String(phase || '').toUpperCase();
    if (Object.prototype.hasOwnProperty.call(IO_PIPELINE, p) || Object.values(IO_PIPELINE).includes(p)) {
      ioPipelinePhase = p;
    } else {
      ioPipelinePhase = p || IO_PIPELINE.IDLE;
    }
    return ioPipelinePhase;
  }

  function isIoPipelineLoading(phase) {
    return LOADING_PHASES.has(String(phase || ioPipelinePhase || '').toUpperCase());
  }

  function ioPipelineBannerText(phase, opts = {}) {
    const p = String(phase || ioPipelinePhase || '').toUpperCase();
    if (LOADING_PHASES.has(p)) {
      if (opts.loadingDetail) return String(opts.loadingDetail);
      const labels = {
        LOADING_ARCHIVE: 'Loading archive…',
        TOPOLOGY_READY: 'Hardware topology ready — parsing claims…',
        PARSING_CLAIMS: 'Parsing I/O claims…',
        RESOLVING_CLAIMS: 'Resolving I/O claims…',
        BUILDING_MODEL: 'Building hardware I/O model…',
      };
      return labels[p] || 'Loading I/O…';
    }
    if (p === IO_PIPELINE.FAILED) {
      return opts.discoveryWarning
        || 'I/O CLAIM DISCOVERY FAILED — hardware topology loaded, claim inventory incomplete';
    }
    if (p === IO_PIPELINE.REVIEW_REQUIRED) {
      return opts.discoveryWarning || 'I/O CLAIM REVIEW REQUIRED';
    }
    return '';
  }

  /** Map a finished hardware-io model onto a terminal pipeline phase. */
  function resolveIoPipelineFromModel(data) {
    if (!data || data.success === false) return IO_PIPELINE.FAILED;
    const disc = String(
      data.claim_discovery_status || data.stats?.claim_discovery_status || '',
    ).toUpperCase();
    if (disc === 'FAILED' || disc === 'DISCOVERY_FAILURE') return IO_PIPELINE.FAILED;
    if (disc === 'REVIEW_REQUIRED') return IO_PIPELINE.REVIEW_REQUIRED;
    return IO_PIPELINE.READY;
  }

  function autogenBuildKey(r) {
    if (!r || typeof r !== 'object') return '';
    return String(
      r.build_id
      || r.l5x_sha256
      || r.manifest?.output_sha256
      || r.canonical_path
      || r.l5x
      || '',
    ).trim();
  }

  function shouldPresentAutogenCard(r) {
    const key = autogenBuildKey(r);
    if (!key) return true;
    return !presentedBuildKeys.has(key);
  }

  function markAutogenCardPresented(r) {
    const key = autogenBuildKey(r);
    if (key) {
      presentedBuildKeys.add(key);
      lastPresentedBuildKey = key;
    }
    return key;
  }

  function resetAutogenCardDedupe() {
    presentedBuildKeys = new Set();
    lastPresentedBuildKey = '';
  }

  function twinGapScopeKey(s) {
    return sessionKey(s || active);
  }

  function getTwinGapScope() {
    return twinGapScope;
  }

  function setTwinGapScopeFromActive() {
    twinGapScope = sessionKey(active);
    return twinGapScope;
  }

  /** Engineer area names are intentional — never purge "weird" tokens like Area_1lksadfj. */
  function shouldPreserveEngineerAreaName(name) {
    const n = String(name || '').trim();
    if (!n) return false;
    // Only reject empty / pure whitespace. No "sanitize weird names" purge.
    return true;
  }

  const api = {
    IO_PIPELINE,
    getActiveSiteSession,
    sessionEquals,
    sessionKey,
    beginSiteSession,
    bindSiteSessionIdentity,
    invalidateSiteSession,
    tagWithSession,
    acceptAsyncResult,
    getIoPipelinePhase,
    setIoPipelinePhase,
    isIoPipelineLoading,
    ioPipelineBannerText,
    resolveIoPipelineFromModel,
    autogenBuildKey,
    shouldPresentAutogenCard,
    markAutogenCardPresented,
    resetAutogenCardDedupe,
    twinGapScopeKey,
    getTwinGapScope,
    setTwinGapScopeFromActive,
    shouldPreserveEngineerAreaName,
    _test: {
      getPresentedKeys: () => [...presentedBuildKeys],
      getLastPresentedKey: () => lastPresentedBuildKey,
      setActive: (s) => { active = cloneSession(s); twinGapScope = sessionKey(active); },
      reset: () => {
        active = { archive_sha: '', machine: '', loadEpoch: 0 };
        ioPipelinePhase = IO_PIPELINE.IDLE;
        presentedBuildKeys = new Set();
        lastPresentedBuildKey = '';
        twinGapScope = '';
      },
    },
  };

  root.SiteSession = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
