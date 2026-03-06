/**
 * ToastManager - lightweight, works with server-rendered .pm-toast inside #toast-area
 * API: ToastManager.show(type, content, opts) -> id
 *      ToastManager.dismiss(id)
 *      ToastManager.clearAll()
 *
 * opts: { timeout: ms (default 8000), sticky: bool, priority: number, html: bool }
 */

(function () {
  const DEFAULT_TIMEOUT = 8000;
  const MAX_VISIBLE = 4;
  const AREA_ID = 'toast-area';
  const TOAST_CLASS = 'pm-toast';
  const TIMEOUTS = new WeakMap();
  const VISIBLE = new Map(); // id -> element
  const QUEUE = [];
  let idCounter = 1;

  function makeId() {
    return `tm_${Date.now()}_${idCounter++}`;
  }

  function sanitizeType(type) {
    if (!type) return 'info';
    const t = String(type).toLowerCase();
    if (['success','danger','warning','info','primary','secondary','light','dark'].includes(t)) return t;
    if (t === 'error') return 'danger';
    return 'info';
  }

  function getArea() {
    let area = document.getElementById(AREA_ID);
    if (!area) {
      area = document.createElement('div');
      area.id = AREA_ID;
      area.setAttribute('aria-live', 'polite');
      area.setAttribute('aria-atomic', 'true');
      // keep minimal inline layout if template didn't provide wrapper
      area.style.position = 'fixed';
      area.style.top = '1rem';
      area.style.right = '1rem';
      area.style.zIndex = '1080';
      area.style.display = 'flex';
      area.style.flexDirection = 'column';
      area.style.gap = '.5rem';
      area.style.alignItems = 'flex-end';
      document.body.appendChild(area);
    }
    return area;
  }

  function createToastNode(id, type, content, opts) {
    const div = document.createElement('div');
    div.className = `${TOAST_CLASS} alert alert-${sanitizeType(type)} d-flex align-items-start shadow-sm`;
    div.setAttribute('role', 'alert');
    div.setAttribute('data-tm-id', id);

    const body = document.createElement('div');
    body.className = 'pm-toast-body';

    const contentWrap = document.createElement('div');
    contentWrap.style.flex = '1';
    if (opts && opts.html) contentWrap.innerHTML = content;
    else contentWrap.textContent = content || '';

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close ms-2';
    closeBtn.setAttribute('aria-label', 'Close');

    body.appendChild(contentWrap);
    body.appendChild(closeBtn);
    div.appendChild(body);

    closeBtn.addEventListener('click', () => {
      const tid = div.getAttribute('data-tm-id');
      if (tid) dismiss(tid);
    });

    div.addEventListener('mouseenter', () => clearScheduled(div));
    div.addEventListener('mouseleave', () => {
      if (!opts || !opts.sticky) {
        const t = (opts && typeof opts.timeout === 'number') ? opts.timeout : DEFAULT_TIMEOUT;
        scheduleHide(div, t);
      }
    });

    return div;
  }

  function scheduleHide(el, delay) {
    clearScheduled(el);
    const to = setTimeout(() => {
      removeElement(el);
    }, delay);
    TIMEOUTS.set(el, to);
  }

  function clearScheduled(el) {
    const to = TIMEOUTS.get(el);
    if (to) {
      clearTimeout(to);
      TIMEOUTS.delete(el);
    }
  }

  function removeElement(el) {
    if (!el || !el.parentNode) return;
    const FADE_MS = 220;
    el.style.transition = `transform ${FADE_MS}ms ease, opacity ${FADE_MS}ms ease`;
    el.style.transform = 'translateX(20px)';
    el.style.opacity = '0';
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, FADE_MS + 10);

    const id = el.getAttribute('data-tm-id');
    if (id && VISIBLE.has(id)) VISIBLE.delete(id);
    showFromQueue();
  }

  function showFromQueue() {
    const area = getArea();
    while (VISIBLE.size < MAX_VISIBLE && QUEUE.length) {
      // pick highest priority
      let bestIdx = 0;
      for (let i = 1; i < QUEUE.length; i++) {
        if ((QUEUE[i].opts?.priority || 0) > (QUEUE[bestIdx].opts?.priority || 0)) bestIdx = i;
      }
      const item = QUEUE.splice(bestIdx, 1)[0];
      const node = createToastNode(item.id, item.type, item.content, item.opts || {});
      area.insertBefore(node, area.firstChild);
      // allow CSS transition
      requestAnimationFrame(() => node.classList.add('show-toast'));
      VISIBLE.set(item.id, node);
      if (!item.opts || !item.opts.sticky) {
        const t = typeof item.opts?.timeout === 'number' ? item.opts.timeout : DEFAULT_TIMEOUT;
        scheduleHide(node, t);
      }
    }
  }

  function show(type, content, opts = {}) {
    const id = makeId();
    const entry = { id, type, content, opts };
    if (VISIBLE.size < MAX_VISIBLE) {
      const area = getArea();
      const node = createToastNode(id, type, content, opts);
      area.insertBefore(node, area.firstChild);
      requestAnimationFrame(() => node.classList.add('show-toast'));
      VISIBLE.set(id, node);
      if (!opts.sticky) {
        const t = typeof opts.timeout === 'number' ? opts.timeout : DEFAULT_TIMEOUT;
        scheduleHide(node, t);
      }
    } else {
      QUEUE.push(entry);
    }
    return id;
  }

  function dismiss(id) {
    if (!id) return false;
    const el = VISIBLE.get(id);
    if (el) {
      removeElement(el);
      return true;
    }
    const qi = QUEUE.findIndex(x => x.id === id);
    if (qi >= 0) { QUEUE.splice(qi, 1); return true; }
    return false;
  }

  function clearAll() {
    VISIBLE.forEach(el => {
      clearScheduled(el);
      if (el.parentNode) el.parentNode.removeChild(el);
    });
    VISIBLE.clear();
    QUEUE.length = 0;
  }

  // Initialize existing server-rendered toasts inside #toast-area
  function initFromDOM() {
    document.addEventListener('DOMContentLoaded', () => {
      const area = getArea();
      // if server rendered messages are inside area, pick them
      const toasts = Array.from(area.querySelectorAll(`.${TOAST_CLASS}`));
      toasts.forEach((t, i) => {
        let tid = t.getAttribute('data-tm-id');
        if (!tid) {
          tid = makeId();
          t.setAttribute('data-tm-id', tid);
        }
        // wire close if present
        const btn = t.querySelector('.btn-close');
        if (btn) {
          btn.addEventListener('click', () => {
            const id = t.getAttribute('data-tm-id');
            if (id) dismiss(id);
          });
        }
        t.addEventListener('mouseenter', () => clearScheduled(t));
        t.addEventListener('mouseleave', () => scheduleHide(t, DEFAULT_TIMEOUT));
        // show with small stagger
        setTimeout(() => t.classList.add('show-toast'), 40 * i);
        scheduleHide(t, DEFAULT_TIMEOUT + 40 * i);
        VISIBLE.set(t.getAttribute('data-tm-id'), t);
      });
    });
  }

  // Observe dynamically added elements (e.g., templates injecting .pm-toast after load)
  function observeDOM() {
    const obs = new MutationObserver(muts => {
      muts.forEach(m => {
        m.addedNodes.forEach(node => {
          if (!(node instanceof Element)) return;
          if (node.matches && node.matches(`.${TOAST_CLASS}`)) {
            const tid = node.getAttribute('data-tm-id') || makeId();
            node.setAttribute('data-tm-id', tid);
            const btn = node.querySelector('.btn-close');
            if (btn) btn.addEventListener('click', () => dismiss(tid));
            node.addEventListener('mouseenter', () => clearScheduled(node));
            node.addEventListener('mouseleave', () => scheduleHide(node, DEFAULT_TIMEOUT));
            setTimeout(() => {
              node.classList.add('show-toast');
              scheduleHide(node, DEFAULT_TIMEOUT);
              VISIBLE.set(tid, node);
            }, 20);
          } else if (node.querySelectorAll) {
            const nested = node.querySelectorAll(`.${TOAST_CLASS}`);
            nested.forEach(n => {
              const tid = n.getAttribute('data-tm-id') || makeId();
              n.setAttribute('data-tm-id', tid);
              const btn = n.querySelector('.btn-close');
              if (btn) btn.addEventListener('click', () => dismiss(tid));
              n.addEventListener('mouseenter', () => clearScheduled(n));
              n.addEventListener('mouseleave', () => scheduleHide(n, DEFAULT_TIMEOUT));
              setTimeout(() => {
                n.classList.add('show-toast');
                scheduleHide(n, DEFAULT_TIMEOUT);
                VISIBLE.set(tid, n);
              }, 20);
            });
          }
        });
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  // Expose
  window.ToastManager = {
    show,
    dismiss,
    clearAll,
    _state: () => ({ visible: Array.from(VISIBLE.keys()), queue: QUEUE.map(q => ({ id: q.id, priority: q.opts?.priority || 0 })) })
  };

  // Boot
  initFromDOM();
  observeDOM();
})();