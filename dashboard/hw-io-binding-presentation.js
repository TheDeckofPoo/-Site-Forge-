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

  root.formatIoEquipmentBindingView = formatIoEquipmentBindingView;
  root.equipmentBindingDetailLines = equipmentBindingDetailLines;
  root.hwIoBindingPresentation = {
    formatIoEquipmentBindingView,
    equipmentBindingDetailLines,
    CLASS_LABELS,
    memberFromPath,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.hwIoBindingPresentation;
  }
})(typeof window !== 'undefined' ? window : globalThis);
