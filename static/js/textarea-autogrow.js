/* 댓글·답글 입력창: 크기 조절 손잡이 없이 글자 수에 맞춰 높이가 자동으로 늘고 줄어든다. */
(() => {
  'use strict';
  const SELECTOR = 'textarea.comment-textarea, .comment-form textarea';
  const MAX_VIEWPORT_RATIO = 0.6;

  function fit(textarea) {
    if (!textarea.offsetParent) return; // 숨겨진 답글 입력창은 열릴 때 맞춘다
    textarea.style.height = 'auto';
    const max = Math.max(160, window.innerHeight * MAX_VIEWPORT_RATIO);
    const next = Math.min(textarea.scrollHeight + (textarea.offsetHeight - textarea.clientHeight), max);
    textarea.style.height = next + 'px';
    textarea.style.overflowY = textarea.scrollHeight > max ? 'auto' : 'hidden';
  }
  function fitAll() { document.querySelectorAll(SELECTOR).forEach(fit); }

  document.addEventListener('input', event => {
    if (event.target.matches?.(SELECTOR)) fit(event.target);
  });
  document.addEventListener('focusin', event => {
    if (event.target.matches?.(SELECTOR)) fit(event.target);
  });
  window.addEventListener('resize', fitAll);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fitAll, {once: true});
  else fitAll();
})();
