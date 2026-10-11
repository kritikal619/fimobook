/* 댓글 등록·삭제처럼 같은 페이지로 돌아오는 POST 폼을 기록(history)에 새 항목을 남기지 않고 처리한다.
   일반 제출은 POST 후 리다이렉트로 항목이 하나씩 쌓여서, 댓글을 여러 개 달면 뒤로가기를 그만큼 눌러야 했다.
   처리 뒤 페이지를 다시 불러오되, 보던 스크롤 위치를 그대로 되돌려 놓는다. */
(() => {
  'use strict';
  const KEY = 'samePageScroll';

  // 다시 불러온 직후: 저장해 둔 스크롤 위치로 복원
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    sessionStorage.removeItem(KEY);
    if (saved && saved.path === location.pathname + location.search && Date.now() - saved.at < 15000) {
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      const restore = () => window.scrollTo(0, saved.y);
      restore();
      document.addEventListener('DOMContentLoaded', restore, {once: true});
      window.addEventListener('load', () => { restore(); if ('scrollRestoration' in history) history.scrollRestoration = 'auto'; }, {once: true});
    }
  } catch (_) { /* 저장소를 못 쓰면 기본 동작 */ }

  document.addEventListener('submit', async event => {
    const form = event.target.closest?.('form[data-same-page]');
    if (!form || event.defaultPrevented || !window.fetch || !window.FormData) return;
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter && submitter.disabled) return;
    if (submitter) submitter.disabled = true;
    try {
      const data = new FormData(form);
      if (submitter && submitter.name) data.append(submitter.name, submitter.value);
      // 리다이렉트는 따라가지 않는다. 서버 처리(저장·알림 메시지)만 끝내고 현재 페이지를 같은 자리에서 다시 불러온다.
      await fetch(form.action, {method: 'POST', body: data, credentials: 'same-origin', redirect: 'manual'});
      try {
        sessionStorage.setItem(KEY, JSON.stringify({path: location.pathname + location.search, y: window.scrollY, at: Date.now()}));
      } catch (_) { /* 무시 */ }
      location.reload();
    } catch (_) {
      if (submitter) submitter.disabled = false;
      form.submit(); // 네트워크 문제 등은 원래 방식으로 처리
    }
  });
})();
