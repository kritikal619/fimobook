(() => {
  const root = document.querySelector('[data-player-finder]');
  if (!root) return;

  const form = root.querySelector('[data-finder-form]');
  const queryInput = form.elements.q;
  const sortSelect = root.querySelector('[data-sort-select]');
  const results = root.querySelector('[data-player-results]');
  const count = root.querySelector('[data-result-count]');
  const loading = root.querySelector('[data-loading-line]');
  const message = root.querySelector('[data-result-message]');
  const loadMoreButton = root.querySelector('[data-load-more]');
  const activeFilters = root.querySelector('[data-active-filters]');
  const clearSearch = root.querySelector('[data-clear-search]');
  const suggestions = root.querySelector('.suggestion-list');
  const filterPanel = root.querySelector('[data-filter-panel]');
  const filterBackdrop = root.querySelector('[data-filter-backdrop]');
  const openFilterButton = root.querySelector('[data-open-filter]');
  const closeFilterButton = root.querySelector('[data-close-filter]');
  const filterCount = root.querySelector('[data-filter-count]');
  const searchApi = root.dataset.searchApi;
  const autocompleteApi = root.dataset.autocompleteApi;
  const detailTemplate = root.dataset.detailTemplate;

  let resultLimit = 24;
  let searchController;
  let suggestionController;
  let suggestionTimer;
  let activeSuggestion = -1;
  let filterTrigger;

  const numberFormat = new Intl.NumberFormat('ko-KR');
  const compactNumberFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });
  const svgArrow = () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('result-arrow');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'm9 18 6-6-6-6');
    svg.append(path);
    return svg;
  };

  function setText(element, value, fallback = '—') {
    element.textContent = value === null || value === undefined || value === '' ? fallback : String(value);
  }

  function formatPrice(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return '—';
    if (number >= 100000000) return `${compactNumberFormat.format(number / 100000000)}억 MP`;
    if (number >= 10000) return `${compactNumberFormat.format(number / 10000)}만 MP`;
    return `${numberFormat.format(number)} MP`;
  }

  function restoreFormFromUrl() {
    const params = new URLSearchParams(window.location.search);
    for (const element of Array.from(form.elements)) {
      if (!element.name) continue;
      if (element.type === 'checkbox') {
        element.checked = params.getAll(element.name).includes(element.value);
      } else if (params.has(element.name)) {
        element.value = params.get(element.name);
      }
    }
  }

  function getParams() {
    const params = new URLSearchParams();
    for (const [name, rawValue] of new FormData(form).entries()) {
      const value = String(rawValue).trim();
      if (value) params.append(name, value);
    }
    params.set('limit', String(resultLimit));
    return params;
  }

  function updateAddress(params) {
    const visibleParams = new URLSearchParams(params);
    visibleParams.delete('limit');
    const query = visibleParams.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  }

  function filterLabel(name, value) {
    const labels = {
      q: `이름: ${value}`,
      position: value,
      player_class: value,
      min_ovr: `OVR ${value} 이상`,
      max_ovr: `OVR ${value} 이하`,
    };
    return labels[name] || value;
  }

  function updateFilterChips() {
    activeFilters.replaceChildren();
    const params = getParams();
    params.delete('limit');
    params.delete('sort');
    let appliedCount = 0;
    for (const [name, value] of params.entries()) {
      if (name === 'q') continue;
      appliedCount += 1;
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'filter-chip';
      chip.textContent = filterLabel(name, value);
      chip.setAttribute('aria-label', `${filterLabel(name, value)} 조건 해제`);
      chip.addEventListener('click', () => {
        for (const element of Array.from(form.elements)) {
          if (element.name !== name) continue;
          if (element.type === 'checkbox') {
            if (element.value === value) element.checked = false;
          } else {
            element.value = '';
          }
        }
        resultLimit = 24;
        loadPlayers();
      });
      activeFilters.append(chip);
    }
    filterCount.textContent = String(appliedCount);
    filterCount.hidden = appliedCount === 0;
    clearSearch.hidden = !queryInput.value;
  }

  function createPlayerRow(player) {
    const link = document.createElement('a');
    link.className = 'player-result';
    link.href = detailTemplate.replace('999999999', encodeURIComponent(player.cid));

    const art = document.createElement('div');
    art.className = 'result-art';
    art.dataset.fimoCardCid = String(player.cid);
    const cardImage = player.bimageThumb || player.bimage || '';
    const faceImage = player.pimageThumb || player.pimage || '';
    const hasCard = cardImage && !String(cardImage).includes('card-background-placeholder');
    const hasFace = faceImage && !/(apple-touch-icon|favicon)/.test(String(faceImage));
    if (hasCard) art.style.backgroundImage = `url("${String(cardImage).replaceAll('"', '%22')}")`;
    if (hasFace) {
      const image = document.createElement('img');
      image.src = faceImage;
      image.alt = '';
      image.loading = 'lazy';
      image.decoding = 'async';
      art.append(image);
    } else if (!hasCard) {
      art.classList.add('is-placeholder');
      const initial = document.createElement('span');
      initial.textContent = String(player.playerKor || '?').trim().charAt(0) || '?';
      art.append(initial);
    }

    const main = document.createElement('div');
    main.className = 'result-main';
    const name = document.createElement('strong');
    setText(name, player.playerKor, '이름 미확인');
    const classLine = document.createElement('div');
    classLine.className = 'class-line';
    const playerClass = document.createElement('b');
    setText(playerClass, player.className, '클래스 미확인');
    const position = document.createElement('span');
    setText(position, player.position, '포지션 미확인');
    classLine.append(playerClass, position);
    const team = document.createElement('span');
    team.className = 'team-line';
    setText(team, player.team || player.nation, '소속 정보 없음');
    main.append(name, classLine, team);

    const ovr = document.createElement('div');
    ovr.className = 'result-ovr';
    const ovrLabel = document.createElement('small');
    ovrLabel.textContent = 'OVR';
    const ovrValue = document.createElement('strong');
    setText(ovrValue, player.ovr);
    ovr.append(ovrLabel, ovrValue);

    const price = document.createElement('div');
    price.className = 'result-price';
    const priceLabel = document.createElement('small');
    priceLabel.textContent = '기준가';
    const priceValue = document.createElement('strong');
    priceValue.textContent = formatPrice(player.price);
    price.append(priceLabel, priceValue);

    link.append(art, main, ovr, price, svgArrow());
    return link;
  }

  function showMessage(title, description, canRetry = false) {
    message.replaceChildren();
    const heading = document.createElement('strong');
    heading.textContent = title;
    const detail = document.createElement('span');
    detail.textContent = description;
    message.append(heading, detail);
    if (canRetry) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'secondary-button';
      retry.textContent = '다시 시도';
      retry.addEventListener('click', () => loadPlayers());
      message.append(retry);
    }
    message.hidden = false;
  }

  async function loadPlayers({ append = false } = {}) {
    searchController?.abort();
    searchController = new AbortController();
    if (!append) resultLimit = Math.max(24, resultLimit);
    const params = getParams();
    updateAddress(params);
    updateFilterChips();
    closeSuggestions();
    loading.hidden = false;
    message.hidden = true;
    loadMoreButton.hidden = true;
    results.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(`${searchApi}?${params.toString()}`, { signal: searchController.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const players = await response.json();
      results.replaceChildren(...players.map(createPlayerRow));
      count.textContent = numberFormat.format(players.length);
      if (!players.length) {
        showMessage('조건에 맞는 선수가 없어요', '검색어를 바꾸거나 선택한 조건을 줄여보세요.');
      }
      loadMoreButton.hidden = players.length < resultLimit || resultLimit >= 60;
    } catch (error) {
      if (error.name === 'AbortError') return;
      count.textContent = '—';
      showMessage('선수 정보를 불러오지 못했어요', '잠시 후 다시 시도해 주세요.', true);
    } finally {
      loading.hidden = true;
      results.removeAttribute('aria-busy');
    }
  }

  function closeSuggestions() {
    suggestions.hidden = true;
    suggestions.replaceChildren();
    queryInput.setAttribute('aria-expanded', 'false');
    activeSuggestion = -1;
  }

  async function loadSuggestions() {
    const value = queryInput.value.trim();
    clearSearch.hidden = !value;
    if (value.length < 2) return closeSuggestions();
    suggestionController?.abort();
    suggestionController = new AbortController();
    try {
      const response = await fetch(`${autocompleteApi}?q=${encodeURIComponent(value)}`, { signal: suggestionController.signal });
      if (!response.ok) throw new Error();
      const names = await response.json();
      suggestions.replaceChildren();
      names.forEach((item) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.setAttribute('role', 'option');
        option.textContent = item.playerKor;
        option.addEventListener('click', () => {
          queryInput.value = item.playerKor;
          closeSuggestions();
          resultLimit = 24;
          loadPlayers();
        });
        suggestions.append(option);
      });
      suggestions.hidden = !names.length;
      queryInput.setAttribute('aria-expanded', names.length ? 'true' : 'false');
    } catch (error) {
      if (error.name !== 'AbortError') closeSuggestions();
    }
  }

  function moveSuggestion(direction) {
    const options = Array.from(suggestions.querySelectorAll('button'));
    if (!options.length) return;
    activeSuggestion = (activeSuggestion + direction + options.length) % options.length;
    options.forEach((option, index) => option.classList.toggle('is-active', index === activeSuggestion));
    options[activeSuggestion].scrollIntoView({ block: 'nearest' });
  }

  function openFilters() {
    filterTrigger = document.activeElement;
    filterPanel.classList.add('is-open');
    filterBackdrop.hidden = false;
    document.body.classList.add('is-filter-open');
    openFilterButton.setAttribute('aria-expanded', 'true');
    closeFilterButton.focus();
  }

  function closeFilters() {
    filterPanel.classList.remove('is-open');
    filterBackdrop.hidden = true;
    document.body.classList.remove('is-filter-open');
    openFilterButton.setAttribute('aria-expanded', 'false');
    if (filterTrigger) filterTrigger.focus();
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    resultLimit = 24;
    closeFilters();
    loadPlayers();
  });
  form.addEventListener('reset', () => window.setTimeout(() => {
    resultLimit = 24;
    loadPlayers();
  }, 0));
  sortSelect.addEventListener('change', () => {
    resultLimit = 24;
    loadPlayers();
  });
  clearSearch.addEventListener('click', () => {
    queryInput.value = '';
    clearSearch.hidden = true;
    queryInput.focus();
    resultLimit = 24;
    loadPlayers();
  });
  queryInput.addEventListener('input', () => {
    window.clearTimeout(suggestionTimer);
    suggestionTimer = window.setTimeout(loadSuggestions, 160);
  });
  queryInput.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); moveSuggestion(1); }
    if (event.key === 'ArrowUp') { event.preventDefault(); moveSuggestion(-1); }
    if (event.key === 'Escape') closeSuggestions();
    if (event.key === 'Enter' && activeSuggestion >= 0) {
      const option = suggestions.querySelectorAll('button')[activeSuggestion];
      if (option) { event.preventDefault(); option.click(); }
    }
  });
  loadMoreButton.addEventListener('click', () => {
    resultLimit = Math.min(60, resultLimit + 12);
    loadPlayers({ append: true });
  });
  openFilterButton.addEventListener('click', openFilters);
  closeFilterButton.addEventListener('click', closeFilters);
  filterBackdrop.addEventListener('click', closeFilters);
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.search-box')) closeSuggestions();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && filterPanel.classList.contains('is-open')) closeFilters();
  });

  restoreFormFromUrl();
  loadPlayers();
})();
