/**
 * Subsystem generation status cards for Site Forge.
 * Status vocabulary (legacy export cards):
 *   READY | CONFIGURATION REQUIRED | PARTIAL GENERATION |
 *   GENERATION NOT SUPPORTED | BLOCKED | N/A
 *
 * Compile-hub readiness vocabulary (Apply-per-tab):
 *   NOT DETECTED | DETECTED — REVIEW REQUIRED | READY FOR AUTOGEN |
 *   CHANGED SINCE LAST APPLY | ERROR / BLOCKED
 *
 * Prefer server/export JSON: exports/integration-hardening/ui_subsystem_status.json
 * Do not invent CP5-specific buttons — same Import→Discover→Review→Build flow.
 */
(function (global) {
  const ORDER = ["Transport", "Safety", "Sawtooth", "Sorter", "WCS"];
  const HUB_ORDER = ["hardware", "transport", "sawtooth", "sorter", "system"];
  const HUB_LABELS = {
    hardware: "Hardware / IO",
    transport: "Transportation",
    sawtooth: "Sawtooth",
    sorter: "Sorter",
    system: "System / Core",
  };
  const HUB_DISPLAY = {
    NOT_DETECTED: "NOT DETECTED",
    REVIEW_REQUIRED: "DETECTED — REVIEW REQUIRED",
    CHANGED: "CHANGED SINCE LAST APPLY",
    READY: "READY FOR AUTOGEN",
    ERROR: "ERROR / BLOCKED",
  };

  function normalizeStatus(s) {
    const u = String(s || "").toUpperCase();
    if (u === "N/A" || u === "NA") return "N/A";
    if (u.includes("BLOCK")) return "BLOCKED";
    if (u.includes("NOT SUPPORT")) return "GENERATION NOT SUPPORTED";
    if (u.includes("PARTIAL")) return "PARTIAL GENERATION";
    if (u.includes("CONFIG")) return "CONFIGURATION REQUIRED";
    if (u.includes("READY")) return "READY";
    return String(s || "CONFIGURATION REQUIRED");
  }

  function normalizeHubStatus(s) {
    const u = String(s || "").toUpperCase().replace(/[—–]/g, "-");
    if (u.includes("ERROR") || u.includes("BLOCK")) return "ERROR";
    if (u.includes("CHANGED")) return "CHANGED";
    if (u.includes("READY")) return "READY";
    if (u.includes("REVIEW") || u.includes("DETECT")) return "REVIEW_REQUIRED";
    if (u.includes("NOT DETECT") || u === "N/A" || u === "NA") return "NOT_DETECTED";
    return "REVIEW_REQUIRED";
  }

  function hubDisplayLabel(status) {
    return HUB_DISPLAY[normalizeHubStatus(status)] || HUB_DISPLAY.REVIEW_REQUIRED;
  }

  function statusClass(status) {
    switch (normalizeStatus(status)) {
      case "READY":
        return "ss-ready";
      case "CONFIGURATION REQUIRED":
        return "ss-cfg";
      case "PARTIAL GENERATION":
        return "ss-partial";
      case "GENERATION NOT SUPPORTED":
        return "ss-nosup";
      case "BLOCKED":
        return "ss-blocked";
      case "N/A":
        return "ss-na";
      default:
        return "ss-cfg";
    }
  }

  function hubStatusClass(status) {
    switch (normalizeHubStatus(status)) {
      case "READY":
        return "ss-ready";
      case "CHANGED":
      case "REVIEW_REQUIRED":
        return "ss-cfg";
      case "ERROR":
        return "ss-blocked";
      case "NOT_DETECTED":
        return "ss-na";
      default:
        return "ss-cfg";
    }
  }

  function renderSubsystemStatus(container, statusMap) {
    if (!container) return;
    const map = statusMap || {};
    container.innerHTML = ORDER.map((name) => {
      const st = normalizeStatus(map[name]);
      return (
        `<div class="ss-card ${statusClass(st)}" data-subsystem="${name}">` +
        `<div class="ss-name">${name}</div>` +
        `<div class="ss-status">${st}</div>` +
        `</div>`
      );
    }).join("");
  }

  /** Render compile-hub readiness map: { hardware: {status, detail, appliedAt, unresolved}, ... } */
  function renderHubReadiness(container, readinessMap) {
    if (!container) return;
    const map = readinessMap || {};
    container.innerHTML = HUB_ORDER.map((key) => {
      const e = map[key] || {};
      const st = normalizeHubStatus(e.status);
      const label = hubDisplayLabel(st);
      const detail = e.detail || "";
      const extra = st === "REVIEW_REQUIRED" && e.unresolved
        ? ` · ${e.unresolved} unresolved`
        : (st === "READY" && e.appliedAt ? ` · applied ${e.appliedAt}` : "");
      return (
        `<div class="ss-card ${hubStatusClass(st)}" data-ready-key="${key}" data-status="${st}">` +
        `<div class="ss-name">${HUB_LABELS[key] || key}</div>` +
        `<div class="ss-status">${label}</div>` +
        (detail || extra
          ? `<div class="text-[9px] text-slate-600 mt-1">${detail}${extra}</div>`
          : "") +
        `</div>`
      );
    }).join("");
  }

  global.SiteForgeSubsystemStatus = {
    ORDER,
    HUB_ORDER,
    HUB_LABELS,
    HUB_DISPLAY,
    normalizeStatus,
    normalizeHubStatus,
    hubDisplayLabel,
    statusClass,
    hubStatusClass,
    renderSubsystemStatus,
    renderHubReadiness,
  };
})(typeof window !== "undefined" ? window : globalThis);
