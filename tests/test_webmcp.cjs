const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/webmcp.js'), 'utf8');
const origin = 'https://fcbook.info';

function load({ legacy = false, unsupported = false, fetchImpl = fetch, failRegistration = false } = {}) {
  const tools = new Map();
  const warnings = [];
  const context = { registerTool(tool) {
    if (failRegistration && tool.name === 'fimobook_get_player') throw new Error('Registration denied');
    tools.set(tool.name, tool);
  } };
  vm.runInNewContext(source, {
    document: legacy || unsupported ? {} : { modelContext: context },
    navigator: legacy ? { modelContext: context } : {},
    location: { origin }, URL, AbortController, setTimeout, clearTimeout,
    fetch: fetchImpl, console: { warn: (...args) => warnings.push(args) },
  });
  const call = (name, input, options) => tools.get(`fimobook_${name}`).execute(input, options);
  return { tools, warnings, call };
}

async function main() {
  let requests = [];
  const mockFetch = async (url, options) => {
    requests.push({ url: new URL(url), options });
    if (options.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    let data;
    if (url.pathname === '/api/squad_players') data = [{ cid: 101, playerKor: '선수', price: null, priceByEnhance: { 5: 500 } }];
    else if (url.pathname === '/api/player_compare') data = { player: { cid: Number(url.searchParams.get('cid')) }, stat_groups: {} };
    else if (url.pathname === '/api/player_prices') data = { prices: { 101: { price: null, priceByEnhance: {}, source: 'local', checked_at: null } } };
    else data = [{ code: 'EXAMPLE', boolExpires: true }];
    return { ok: true, json: async () => data };
  };
  const app = load({ fetchImpl: mockFetch });
  assert.equal(app.tools.size, 5);
  assert.equal(load({ legacy: true, fetchImpl: mockFetch }).tools.size, 5);
  assert.equal(load({ unsupported: true, fetchImpl: () => { throw new Error('Must not fetch'); } }).tools.size, 0);
  const denied = load({ failRegistration: true, fetchImpl: mockFetch });
  assert.equal(denied.tools.size, 4);
  assert.equal(denied.warnings.length, 1);
  assert.ok([...app.tools.values()].every(tool => tool.annotations.readOnlyHint));

  const search = await app.call('search_players', { query: '손흥민', class_name: 'ICON', position: 'ST', include_sub_position: true, min_ovr: 100, max_price: 1000, price_enhance: 5, sort: 'price_asc', limit: 3 });
  assert.equal(search.returned_count, 1);
  assert.equal(search.players[0].price, null);
  assert.equal(search.players[0].priceByEnhance[5], 500);
  assert.equal(search.players[0].url, `${origin}/player/101`);
  const params = requests.at(-1).url.searchParams;
  for (const [key, value] of Object.entries({ q: '손흥민', class: 'ICON', position: 'ST', include_sub_position: 'true', min_ovr: '100', max_price: '1000', price_enhance: '5', sort: 'price_asc', limit: '3' })) assert.equal(params.get(key), value);

  const beforeInvalid = requests.length;
  for (const [name, input] of [
    ['get_player', {}], ['get_player', { cid: -1 }], ['get_player', { cid: '101' }],
    ['compare_players', { cids: [101, 101] }], ['compare_players', { cids: [101] }],
    ['get_player_prices', { cids: Array.from({ length: 41 }, (_, i) => i + 1) }],
    ['search_players', { position: 'INVALID' }], ['search_players', { min_price: 100, max_price: 50 }],
    ['search_players', { limit: 61 }], ['get_coupons', { arbitrary_url: '/admin' }],
  ]) assert.ok((await app.call(name, input)).error);
  assert.equal(requests.length, beforeInvalid);
  const details = await app.call('get_player', { cid: 101 });
  assert.equal(details.player.cid, 101);
  const comparison = await app.call('compare_players', { cids: [101, 102] });
  assert.deepEqual(Array.from(comparison.players, item => item.player.cid), [101, 102]);
  const prices = await app.call('get_player_prices', { cids: [101, 999] });
  assert.deepEqual(Array.from(prices.missing_cids), [999]);
  assert.equal(prices.prices[101].price, null);
  assert.equal(prices.prices[101].source, 'local');
  assert.equal((await app.call('get_coupons', {})).coupons[0].boolExpires, true);
  assert.ok(requests.every(item => item.options.method === 'GET' && item.url.origin === origin));

  const controller = new AbortController();
  controller.abort();
  assert.match((await app.call('get_player', { cid: 101 }, { signal: controller.signal })).error, /취소/);
  const httpFailure = load({ fetchImpl: async () => ({ ok: false, status: 404 }) });
  assert.match((await httpFailure.call('get_player', { cid: 101 })).error, /404/);
  const midAbort = load({ fetchImpl: async (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })) });
  const runningController = new AbortController();
  const pending = midAbort.call('get_player', { cid: 101 }, { signal: runningController.signal });
  runningController.abort();
  assert.match((await pending).error, /취소/);
  console.log('PASS: registration, legacy/unsupported browsers, filtering, invalid inputs, comparison, missing prices, HTTP failure and cancellation');

  if (process.argv.includes('--live')) {
    // A registration adapter captures callbacks; HTTP requests use the actual public APIs.
    const live = load();
    const found = await live.call('search_players', { query: '손흥민', limit: 2 });
    assert.ok(!found.error, found.error);
    assert.equal(found.players.length, 2);
    const ids = found.players.map(player => Number(player.cid));
    assert.ok(ids.every(Number.isSafeInteger));
    const detail = await live.call('get_player', { cid: ids[0] });
    assert.ok(!detail.error, detail.error);
    assert.equal(Number(detail.player.cid), ids[0]);
    assert.ok(Object.keys(detail.stat_groups).length > 0);
    const compared = await live.call('compare_players', { cids: ids });
    assert.ok(!compared.error, compared.error);
    assert.equal(compared.players.length, 2);
    const price = await live.call('get_player_prices', { cids: ids });
    assert.ok(!price.error, price.error);
    assert.equal(price.missing_cids.length, 0);
    for (const id of ids) {
      assert.ok(Object.hasOwn(price.prices[id], 'source'));
      assert.ok(Object.hasOwn(price.prices[id], 'checked_at'));
      assert.ok(Object.hasOwn(price.prices[id], 'priceByEnhance'));
    }
    const coupons = await live.call('get_coupons', {});
    assert.ok(!coupons.error, coupons.error);
    assert.ok(Array.isArray(coupons.coupons) && coupons.coupons.length <= 5);
    console.log('PASS: all five WebMCP callbacks against live public APIs; native browser registration is not simulated as verified');
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
