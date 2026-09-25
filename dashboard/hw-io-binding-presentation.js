/**
 * I/O Map equipment-binding presentation helpers.
 *
 * PRESENTATION ONLY — consumes fortna_equipment_binding fields.
 * Never derive M→P / PS classification in the GUI.
 */
(function (root) {
  'use strict';

  const CLASS_LABELS = {
    MOTOR_STARTER: 'Motor Starter',
    CONVEYOR: 'Conveyor',
    POWER_SUPPLY: 'Power Supply',
    AIR_PRESSURE_SWITCH: 'Air Pressure Switch',
    ESTOP: 'E-Stop / Safety',
    PHOTOEYE: 'Photoeye',
    CONTROL_STATION: 'Control Station',
    UNKNOWN_PS_PREFIX: 'Unresolved PS prefix',
  };

  function _s(v) {
    return v == null ? '' : String(v).trim();
  }

  function memberFromPath(memberPath, logixTag) {
    const mp = _s(memberPath);
    const tag = _s(logixTag);
    if (!mp) return '';
    if (tag && mp.toUpperCase().startsWith(`${tag.toUpperCase()}.`)) {
      return mp.slice(tag.length + 1);
    }
    const m = mp.match(/\.([IO]\.[A-Za-z0-9_]+)$/);
    return m ? m[1] : mp;
  }

  /**
   * @param {object|null|undefined} bind  equipment_binding from shared binder
   * @param {object} [opts]
   * @param {string} [opts.rawFallback]  channel sourceName when bind.raw_name missing
   * @returns {object|null} presentation model or null when no binder relationship
   */
  function formatIoEquipmentBindingView(bind, opts) {
    opts = opts || {};
    if (!bind || typeof bind !== 'object') return null;

    const raw = _s(bind.raw_name) || _s(opts.rawFallback);
    const confidence = _s(bind.confidence).toUpperCase() || '';
    const equipmentClass = _s(bind.equipment_class);
    const datatype = _s(bind.datatype);
    const logixTag = _s(bind.logix_tag) || _s(bind.canonical_id);
    const memberPath = _s(bind.member_path);
    const member = memberFromPath(memberPath, logixTag);
    const reviewReason = _s(bind.review_reason);
    const isReview =
      confidence === 'REVIEW_REQUIRED'
      || equipmentClass === 'UNKNOWN_PS_PREFIX'
      || (!!reviewReason && confidence !== 'PROVEN');

    // Ambiguous PS* — raw + review only; never claim PS_UDT
    if (equipmentClass === 'UNKNOWN_PS_PREFIX' || (isReview && !datatype && !memberPath)) {
      return {
        mode: 'review_only',
        raw: raw || _s(bind.canonical_id),
        canonical: '',
        editValue: '',
        udt: '',
        member: '',
        memberPath: '',
        equipmentClass,
        classLabel: CLASS_LABELS[equipmentClass] || equipmentClass || 'Unresolved',
        confidence: confidence || 'REVIEW_REQUIRED',
        reviewReason: reviewReason || 'EQUIPMENT_BINDING_REVIEW',
        drivenConveyor: _s(bind.driven_conveyor),
        drivenConveyorProvenance: _s(bind.driven_conveyor_provenance),
        rule: _s(bind.rule),
        role: _s(bind.role),
        showUdt: false,
        line1Raw: raw || _s(bind.canonical_id) || '—',
        line1Canon: '',
        line2: '',
        confidenceLabel: '⚠ REVIEW REQUIRED',
      };
    }

    if (!raw && !logixTag) return null;

    const showUdt = !!(datatype && (confidence === 'PROVEN' || memberPath || logixTag));
    const line2Parts = [];
    if (showUdt && datatype) line2Parts.push(datatype);
    if (member) line2Parts.push(member);

    return {
      mode: isReview ? 'bound_review' : 'bound',
      raw: raw || '',
      canonical: logixTag || '',
      editValue: logixTag || '',
      udt: datatype,
      member,
      memberPath,
      equipmentClass,
      classLabel: CLASS_LABELS[equipmentClass] || equipmentClass || '',
      confidence: confidence || (isReview ? 'REVIEW_REQUIRED' : 'PROVEN'),
      reviewReason,
      drivenConveyor: _s(bind.driven_conveyor),
      drivenConveyorProvenance: _s(bind.driven_conveyor_provenance),
      rule: _s(bind.rule),
      role: _s(bind.role),
      showUdt,
      line1Raw: raw || '',
      line1Canon: logixTag || '',
      line2: line2Parts.join(' • '),
      confidenceLabel: isReview ? '⚠ REVIEW REQUIRED' : '● PROVEN',
    };
  }

  /**
   * Build hover / detail lines from binder presentation (no invented fields).
   */
  function equipmentBindingDetailLines(view, physicalEndpoint) {
    if (!view) return [];
    const lines = [
      `Raw Fortna:       ${view.raw || '—'}`,
      `Canonical PLC:    ${view.canonical || '—'}`,
      `Class:            ${view.classLabel || view.equipmentClass || '—'}`,
      `UDT:              ${view.showUdt ? (view.udt || '—') : '—'}`,
      `Member:           ${view.member || '—'}`,
      `Generated target: ${view.memberPath || '—'}`,
    ];
    if (view.drivenConveyor) {
      lines.push(`Driven conveyor:  ${view.drivenConveyor}`);
    }
    if (view.rule) lines.push(`Rule:             ${view.rule}`);
    lines.push(`Confidence:       ${view.confidence || '—'}`);
    if (view.reviewReason) lines.push(`Reason:           ${view.reviewReason}`);
    if (physicalEndpoint) lines.push(`Physical endpoint:${'  '}${physicalEndpoint}`);
    return lines;
  }

  /**
   * Gate D — precise REVIEW_REQUIRED warning: state exactly what is unresolved.
   * Never show "E-STOP FAMILY OUTPUT" for a proven INPUT endpoint.
   *
   * @param {object} opts
   * @param {string} [opts.physicalStatus]  e.g. PROVEN / UNRESOLVED
   * @param {string} [opts.direction]       INPUT / OUTPUT / I / O
   * @param {string} [opts.equipmentClass]
   * @param {string} [opts.datatype]
   * @param {string} [opts.role]
   * @param {string} [opts.confidence]
   * @param {string} [opts.reviewReason]
   * @returns {string}
   */
  function formatBindingReviewStatusLine(opts) {
    opts = opts || {};
    const phys = _s(opts.physicalStatus).toUpperCase() || '—';
    const dir = _s(opts.direction).toUpperCase();
    const isInput = dir === 'INPUT' || dir === 'I' || dir === 'IN';
    const isOutput = dir === 'OUTPUT' || dir === 'O' || dir === 'OUT';
    const cls = _s(opts.equipmentClass).toUpperCase();
    const datatype = _s(opts.datatype).toUpperCase();
    const role = _s(opts.role).toUpperCase();
    const conf = _s(opts.confidence).toUpperCase();
    const reason = _s(opts.reviewReason).toUpperCase();

    const isEstopFamily = cls === 'ESTOP'
      || datatype === 'ES_UDT'
      || /ESTOP|E-STOP|ES_UDT|MCR|ESR|ESLS/.test(reason)
      || /ESTOP|E_STOP/.test(cls);

    const parts = [`Physical endpoint ${phys || '—'}`];

    if (isEstopFamily) {
      // Family can be proven while role binding still needs review
      const familyProven = phys === 'PROVEN' || phys === 'ENGINEER' || conf === 'PROVEN'
        || reason.includes('ESTOP_FAMILY') || reason.includes('ROLE');
      parts.push(`E-Stop family ${familyProven ? 'PROVEN' : (conf || 'REVIEW_REQUIRED')}`);

      let roleLabel = 'ES_UDT role';
      if (role) roleLabel = `${role} role`;
      else if (datatype === 'ES_UDT' || reason.includes('ES_UDT') || isEstopFamily) {
        roleLabel = 'ES_UDT role';
      }

      // Do NOT claim OUTPUT for a proven INPUT endpoint
      if (isInput && /OUTPUT/.test(reason)) {
        parts.push(`${roleLabel} REVIEW_REQUIRED`);
      } else if (conf === 'REVIEW_REQUIRED' || reason) {
        parts.push(`${roleLabel} REVIEW_REQUIRED`);
      } else if (role) {
        parts.push(`${roleLabel} ${conf || 'PROVEN'}`);
      } else {
        parts.push(`${roleLabel} REVIEW_REQUIRED`);
      }
    } else if (conf === 'REVIEW_REQUIRED' || reason) {
      // Generic binding review — humanize reason; strip misleading OUTPUT on inputs
      let human = reason
        ? reason.replace(/_/g, ' ')
        : 'binding unresolved';
      if (isInput) human = human.replace(/\bOUTPUT\b/g, 'ROLE');
      if (isOutput && !/OUTPUT/.test(human) && /ESTOP_FAMILY/.test(reason)) {
        human = 'ESTOP FAMILY OUTPUT NEEDS ROLE PROOF';
      }
      parts.push(`Binding REVIEW_REQUIRED — ${human}`);
    }

    return parts.join(' · ');
  }

  /**
   * Gate D / PD-0039 — translate a REVIEW suggestion into a valid accepted binding.
   * Always stamps ENGINEER_ASSIGNED (never PROVEN). Returns null when incomplete.
   *
   * @param {object|null|undefined} bind  existing equipment_binding suggestion
   * @param {object} [opts]
   * @param {string} [opts.role]
   * @param {string} [opts.canonical]
   * @param {string} [opts.rawFallback]
   * @param {string} [opts.disposition]  default ACCEPT_SUGGESTED
   * @returns {object|null}
   */
  function buildAcceptedEquipmentBinding(bind, opts) {
    opts = opts || {};
    const src = (bind && typeof bind === 'object') ? bind : {};
    const role = _s(opts.role || src.role).toUpperCase();
    const canonical = _s(
      opts.canonical
      || src.logix_tag
      || src.canonical_id
    );
    const raw = _s(src.raw_name || opts.rawFallback);
    if (!canonical && !role) return null;

    const memberPath = _s(src.member_path);
    const datatype = _s(src.datatype);
    const equipmentClass = _s(src.equipment_class)
      || (role ? 'ESTOP' : '');
    const out = {
      raw_name: raw || canonical,
      logix_tag: canonical || raw,
      canonical_id: canonical || raw,
      equipment_class: equipmentClass,
      datatype: datatype,
      member_path: memberPath,
      role: role || _s(src.role),
      rule: _s(src.rule) || 'ENGINEER_ACCEPTED_SUGGESTION',
      confidence: 'ENGINEER_ASSIGNED',
      review_reason: '',
      engineer_disposition: _s(opts.disposition) || 'ACCEPT_SUGGESTED',
    };
    if (_s(src.driven_conveyor)) {
      out.driven_conveyor = _s(src.driven_conveyor);
      out.driven_conveyor_provenance = 'ENGINEER_ASSIGNED';
    }
    // Incomplete: need at least a canonical identity for a valid accepted binding
    if (!_s(out.logix_tag) && !_s(out.canonical_id)) return null;
    return out;
  }

  root.formatIoEquipmentBindingView = formatIoEquipmentBindingView;
  root.equipmentBindingDetailLines = equipmentBindingDetailLines;
  root.formatBindingReviewStatusLine = formatBindingReviewStatusLine;
  root.buildAcceptedEquipmentBinding = buildAcceptedEquipmentBinding;
  root.hwIoBindingPresentation = {
    formatIoEquipmentBindingView,
    equipmentBindingDetailLines,
    formatBindingReviewStatusLine,
    buildAcceptedEquipmentBinding,
    CLASS_LABELS,
    memberFromPath,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.hwIoBindingPresentation;
  }
})(typeof window !== 'undefined' ? window : globalThis);
