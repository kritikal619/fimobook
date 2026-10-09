(() => {
  'use strict';
  const token = document.querySelector('meta[name="fimobook-page-token"]')?.content;
  if (!token) return;
  const paths = new Set([
    '/autocomplete', '/api/squad_players', '/api/player_compare',
    '/api/player_details_by_name', '/api/player_prices',
  ]);
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin !== location.origin ||
        (!paths.has(url.pathname) && !url.pathname.startsWith('/api/player_price/'))) {
      return originalFetch(input, init);
    }
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set('X-Fimobook-Page-Token', token);
    return originalFetch(input, { ...init, headers, cache: 'no-store' });
  };
})();
