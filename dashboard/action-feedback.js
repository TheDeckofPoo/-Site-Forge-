/**
 * Shared Apply / save feedback — never silent success.
 * APPLYING… → APPLIED ✓ / APPLY FAILED with toast + brief button state.
 * Stays on the current tab (no auto-navigation).
 */
(function initSfActionFeedback(global) {
  const TOAST_ID = 'sf-action-toast';

  function ensureToast() {
    let el = document.getElementById(TOAST_ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = TOAST_ID;
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText = [
      'display:none',
      'position:fixed',
      'bottom:1.25rem',
      'left:50%',
      'transform:translateX(-50%)',
      'z-index:220',
      'max-width:90vw',
      'padding:0.55rem 1rem',
      'border-radius:0.5rem',
      'border:1px solid rgba(16,185,129,0.45)',
      'background:#0f1a14',
      'color:#d1fae5',
      'font-size:12px',
      'box-shadow:0 8px 24px rgba(0,0,0,0.45)',
      'white-space:pre-wrap',
    ].join(';');
    document.body.appendChild(el);
    return el;
  }

  let _toastTimer = null;
  function showToast(msg, kind) {
    const el = ensureToast();
    el.textContent = msg || '';
    const ok = kind !== 'fail';
    el.style.borderColor = ok ? 'rgba(16,185,129,0.45)' : 'rgba(248,113,113,0.55)';
    el.style.background = ok ? '#0f1a14' : '#1a1010';
    el.style.color = ok ? '#d1fae5' : '#fecaca';
    el.style.display = 'block';
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => {
      el.style.display = 'none';
    }, kind === 'fail' ? 5200 : 2800);
  }

  function restoreBtn(btn, snap) {
    if (!btn || !snap) return;
    if (snap.html != null) btn.innerHTML = snap.html;
    if (snap.disabled != null) btn.disabled = snap.disabled;
    btn.classList.remove('ring-2', 'ring-emerald-400', 'ring-red-400', 'sf-af-applying');
  }

  const api = {
    begin(btn, label) {
      const snap = btn
        ? { html: btn.innerHTML, disabled: btn.disabled }
        : null;
      if (btn) {
        btn.dataset.sfAfSnap = '1';
        btn._sfAfSnap = snap;
        btn.disabled = true;
        btn.classList.add('sf-af-applying');
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i>${label || 'APPLYING…'}`;
      }
      showToast(label || 'APPLYING…', 'busy');
      return snap;
    },
    success(btn, msg, detail) {
      const snap = btn && btn._sfAfSnap;
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('sf-af-applying');
        btn.classList.add('ring-2', 'ring-emerald-400');
        const short = (msg || 'APPLIED ✓').split('\n')[0];
        btn.innerHTML = `<i class="fa-solid fa-check mr-1"></i>${short}`;
        setTimeout(() => restoreBtn(btn, snap), 1600);
      }
      const body = detail ? `${msg || 'APPLIED ✓'}\n${detail}` : (msg || 'APPLIED ✓');
      showToast(body, 'ok');
    },
    fail(btn, reason) {
      const snap = btn && btn._sfAfSnap;
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('sf-af-applying');
        btn.classList.add('ring-2', 'ring-red-400');
        btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1"></i>APPLY FAILED`;
        setTimeout(() => restoreBtn(btn, snap), 2200);
      }
      showToast(`APPLY FAILED${reason ? ` — ${reason}` : ''}`, 'fail');
    },
  };

  global.sfActionFeedback = api;
})(typeof window !== 'undefined' ? window : globalThis);
