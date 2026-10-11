/* 댓글 등록·삭제처럼 같은 페이지로 돌아오는 POST 폼을 기록(history)에 새 항목을 남기지 않고 처리한다.
   일반 제출은 POST 후 리다이렉트로 항목이 하나씩 쌓여서, 댓글을 여러 개 달면 뒤로가기를 그만큼 눌러야 했다. */
(() => {
  'use strict';
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
      // 리다이렉트는 따라가지 않는다. 서버 처리(저장·알림 메시지)만 끝내고, 현재 페이지를 같은 자리에서 다시 불러온다.
      await fetch(form.action, {method: 'POST', body: data, credentials: 'same-origin', redirect: 'manual'});
      const anchor = form.dataset.anchor || '#comments';
      location.replace(location.pathname + location.search + anchor);
      location.reload();
    } catch (_) {
      if (submitter) submitter.disabled = false;
      form.submit(); // 네트워크 문제 등은 원래 방식으로 처리
    }
  });
})();
