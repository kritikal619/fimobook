(() => {
  'use strict';
  const form = document.getElementById('seasonRankingSearch');
  if (!form) return;
  const input = document.getElementById('seasonRankingNickname');
  const clear = document.getElementById('seasonRankingClear');
  const status = document.getElementById('seasonRankingStatus');
  const empty = document.getElementById('seasonRankingEmpty');
  const normalize = value => value.normalize('NFC').trim().toLocaleLowerCase('ko-KR');
  const rows = Array.from(document.querySelectorAll('#seasonRankingRows tr')).map(element => ({
    element, nickname: element.dataset.nickname, key: normalize(element.dataset.nickname), rank: element.dataset.rank
  }));
  function filter() {
    const query = normalize(input.value);
    let count = 0;
    const exact = [];
    for (const row of rows) {
      const matches = !query || row.key.includes(query);
      row.element.hidden = !matches;
      row.element.classList.toggle('srank-exact', !!query && row.key === query);
      if (matches) count++;
      if (query && row.key === query) exact.push(row);
    }
    clear.hidden = !input.value;
    empty.hidden = count > 0;
    status.classList.toggle('srank-status--match', exact.length > 0);
    status.textContent = !query ? `상위 ${rows.length}명 · FC 챔피언`
      : exact.length ? exact.map(row => `${row.nickname} · ${row.rank}위`).join(' ') + (count > exact.length ? ` · 관련 검색 결과 ${count}명` : '')
      : count ? `검색 결과 ${count}명` : '검색 결과가 없습니다.';
  }
  input.addEventListener('input', event => { if (!event.isComposing) filter(); });
  input.addEventListener('compositionend', filter);
  form.addEventListener('submit', event => { event.preventDefault(); filter(); });
  clear.addEventListener('click', () => { input.value = ''; filter(); input.focus(); });
  filter();
})();
