(() => {
  if (new URLSearchParams(location.search).get('draft_saved') === '1') {
    try { ['dashboard', 'quick'].forEach(name => sessionStorage.removeItem(`fimobook-review-draft:${name}`)); } catch (_) {}
  }
  document.querySelectorAll('[data-review-draft]').forEach(form => {
    const key = `fimobook-review-draft:${form.dataset.reviewDraft}`;
    const fields = [...form.querySelectorAll('textarea, input:not([type=hidden])')];
    const status = form.querySelector('[data-draft-status]');
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (saved) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = '이 탭의 작성 중인 초안 복원';
        button.addEventListener('click', () => {
          fields.forEach(field => { if (typeof saved[field.name] === 'string') field.value = saved[field.name]; });
          button.remove(); status.textContent = '초안을 복원했습니다.';
        });
        status.append(button);
      }
    } catch (_) {}
    form.addEventListener('input', () => {
      try { sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(fields.map(f => [f.name, f.value]))));
        status.textContent = '초안 저장됨. 저장 버튼으로 반영하세요.';
      } catch (_) { status.textContent = '초안을 임시 저장하지 못했습니다. 내용을 복사해두세요.'; }
    });
    form.addEventListener('submit', event => {
      const raw = form.elements.review_summary_json?.value.trim();
      if (raw) {
        try { const value = JSON.parse(raw); if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error(); }
        catch (_) { event.preventDefault(); status.textContent = 'JSON 형식을 확인해주세요. 입력 내용은 유지됩니다.'; form.elements.review_summary_json.focus(); }
      }
      if (!raw && !['summary', 'strengths', 'weaknesses'].some(name => form.elements[name]?.value.trim())) {
        event.preventDefault(); status.textContent = '요약 내용을 입력해주세요.';
      }
    });
  });
})();
