/**
 * Canonical Safety device kind classifier — single source for UI surfaces.
 *
 * Kept aligned with tools/scripts/fortna_safety_model.py::_classify_device.
 * Compile Hub, Safety Build, and Autogen readiness MUST use this result.
 * Do not invent parallel ESPB* / ESLS* regexes in fortna-plus.js.
 *
 * Returns: 'ESTOP' | 'ESLS' | 'ESR' | 'MCR' | 'CS' | '' (not a Safety device)
 */
(function (global) {
  'use strict';

  function classifySafetyDeviceKind(name) {
    const u = String(name || '').trim().toUpperCase().replace(/-/g, '_');
    if (!u) return '';
    if (u.startsWith('INT_')) return '';
    if (/(?:^|_)MEM(?:_|$)/.test(u) || u.includes('_NOT_OK')) return '';
    if (/(?:_OK|_RESET)$/.test(u)) return '';
    if (u.includes('ESLS')) return 'ESLS';
    if (
      /^T_\d+ESR\d*(?:_R\d+)?(?:_?AUX)?$/.test(u)
      || /^CP\d+_ESR\d*(?:_R\d+)?(?:_?AUX)?$/.test(u)
      || /^\d+ESR\d+(?:_R\d+)?(?:_?AUX)?$/.test(u)
      || /^ESR\d+(?:_R\d+)?(?:_?AUX)?$/.test(u)
    ) return 'ESR';
    if (/(?:^|_|T_)(?:CP\d+_)?\d*ESR/.test(u)) return '';
    if (
      /^T_\d+MCR(?:\d+(?:_R\d+)?|_R\d+)(?:_?AUX)?$/.test(u)
      || /^CP\d+_MCR(?:\d+(?:_R\d+)?|_R\d+)(?:_?AUX)?$/.test(u)
      || /^\d+MCR(?:\d+(?:_R\d+)?|_R\d+)(?:_?AUX)?$/.test(u)
      || /^MCR\d+(?:_R\d+)?(?:_?AUX)?$/.test(u)
    ) return 'MCR';
    if (/(?:^|_|T_)(?:CP\d+_)?MCR/.test(u) || /^\d+MCR/.test(u)) return '';
    if (/^CP\d+_CS\d*$/.test(u) || /_CS\d*$/.test(u) || u.endsWith('_CS')) return 'CS';
    // E-stop pushbuttons: ESPB24 / ESPB2 (ES+PB — not matched by ES\d alone)
    if (/^ESPB\d/.test(u) || /(^|_)ESPB\d/.test(u)) return 'ESTOP';
    if (
      /^T_\d+ES\d*\w*$/.test(u)
      || /^CP\d+_ES\d*\w*$/.test(u)
      || /^ES\d[\w]*$/.test(u)
      || /^\d+ES\d*\w*$/.test(u)
      || /(^|_)ES\d/.test(u)
      || /^ES[_]?JES/.test(u)
    ) return 'ESTOP';
    return '';
  }

  /** Partition member names into role buckets using the canonical classifier. */
  function partitionSafetyMembersByKind(members) {
    const buckets = {
      ESTOP: [], ESLS: [], ESR: [], MCR: [], CS: [], OTHER: [],
    };
    (members || []).forEach((m) => {
      const name = typeof m === 'string' ? m : (m?.name || '');
      if (!name) return;
      const kind = classifySafetyDeviceKind(name) || 'OTHER';
      (buckets[kind] || buckets.OTHER).push(name);
    });
    return buckets;
  }

  const api = {
    classifySafetyDeviceKind,
    classify: classifySafetyDeviceKind,
    partitionSafetyMembersByKind,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.SiteForgeSafetyClassify = api;
  global.classifySafetyDeviceKind = classifySafetyDeviceKind;
})(typeof window !== 'undefined' ? window : globalThis);
