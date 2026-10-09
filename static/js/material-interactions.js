(() => {
  'use strict';

  if (!document.body.matches('.home-page, .times-page')) return;

  const controls = 'a[href], button, summary, .recent-pill, .autocomplete-item';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function feedback(event) {
    if (event.type === 'pointerdown' && (!event.isPrimary || event.button !== 0)) return;
    if (event.type === 'keydown' && (event.repeat || !['Enter', ' '].includes(event.key))) return;

    const control = event.target.closest(controls);
    if (!control || control.matches(':disabled, [aria-disabled="true"]') || control.closest('[inert]')) return;
    if (event.type === 'keydown' && event.key === ' ' && control.matches('a[href]')) return;

    // Preserve absolutely positioned search buttons and existing card layouts.
    if (getComputedStyle(control).position === 'static') control.style.position = 'relative';
    let layer = control.querySelector(':scope > .material-state-layer');
    if (!layer) {
      layer = document.createElement('span');
      layer.className = 'material-state-layer';
      layer.setAttribute('aria-hidden', 'true');
      control.appendChild(layer);
    }
    layer.replaceChildren();

    const bounds = control.getBoundingClientRect();
    const x = event.type === 'pointerdown' ? event.clientX - bounds.left : bounds.width / 2;
    const y = event.type === 'pointerdown' ? event.clientY - bounds.top : bounds.height / 2;
    const diameter = 2 * Math.hypot(Math.max(x, bounds.width - x), Math.max(y, bounds.height - y));
    const ripple = document.createElement('span');
    ripple.className = 'material-ripple';
    Object.assign(ripple.style, {
      width: `${diameter}px`, height: `${diameter}px`,
      left: `${x - diameter / 2}px`, top: `${y - diameter / 2}px`,
    });
    layer.appendChild(ripple);
    const animation = ripple.animate(
      reducedMotion.matches
        ? [{ opacity: 0.12 }, { opacity: 0 }]
        : [{ transform: 'scale(0)', opacity: 0.12 }, { transform: 'scale(1)', opacity: 0 }],
      { duration: reducedMotion.matches ? 120 : 320, easing: 'cubic-bezier(0.2, 0, 0, 1)' },
    );
    animation.finished.then(() => ripple.remove(), () => ripple.remove());
  }

  // Delegation includes newly rendered watch buttons and search suggestions.
  document.addEventListener('pointerdown', feedback);
  document.addEventListener('keydown', feedback);
})();
