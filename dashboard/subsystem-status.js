/**
 * Subsystem generation status cards for Site Forge.
 * Status vocabulary:
 *   READY | CONFIGURATION REQUIRED | PARTIAL GENERATION |
 *   GENERATION NOT SUPPORTED | BLOCKED | N/A
 *
 * Prefer server/export JSON: exports/integration-hardening/ui_subsystem_status.json
 * Do not invent CP5-specific buttons — same Import→Discover→Review→Build flow.
 */
(function (global) {
  const ORDER = ["Transport", "Safety", "Sawtooth", "Sorter", "WCS"];

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

  global.SiteForgeSubsystemStatus = {
    ORDER,
    normalizeStatus,
    statusClass,
    renderSubsystemStatus,
  };
})(typeof window !== "undefined" ? window : globalThis);
