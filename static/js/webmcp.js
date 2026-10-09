(() => {
  'use strict';

  // Current WebMCP lives on document; early implementations used navigator.
  const context = typeof document.modelContext?.registerTool === 'function'
    ? document.modelContext : navigator.modelContext;
  if (typeof context?.registerTool !== 'function') return;

  const positions = ['ST', 'CF', 'LW', 'RW', 'CAM', 'CM', 'CDM', 'LM', 'RM', 'LB', 'RB', 'LWB', 'RWB', 'CB', 'GK'];
  const cidSchema = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER, description: '선수 카드 ID(cid). 검색 결과에서 가져오세요. 같은 선수도 클래스마다 ID가 다릅니다.' };
  const textSchema = description => ({ type: 'string', maxLength: 120, description });
  const numberSchema = description => ({ type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER, description });
  const objectSchema = (properties, required = []) => ({ type: 'object', properties, required, additionalProperties: false });
  const cidsSchema = (minItems, maxItems) => ({ type: 'array', items: cidSchema, minItems, maxItems, uniqueItems: true });
  const pageUrl = path => new URL(path, location.origin).href;

  // Validate even in browser implementations that do not enforce JSON Schema.
  function validate(value, schema, name = 'input') {
    if (schema.type === 'object') {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${name}: 객체가 필요합니다.`);
      for (const key of schema.required) {
        if (!Object.hasOwn(value, key)) throw new Error(`${key}: 필수 입력입니다.`);
      }
      for (const [key, item] of Object.entries(value)) {
        if (!Object.hasOwn(schema.properties, key)) throw new Error(`${key}: 지원하지 않는 입력입니다.`);
        validate(item, schema.properties[key], key);
      }
    } else if (schema.type === 'array') {
      if (!Array.isArray(value) || value.length < schema.minItems || value.length > schema.maxItems) throw new Error(`${name}: ${schema.minItems}~${schema.maxItems}개를 입력하세요.`);
      if (schema.uniqueItems && new Set(value).size !== value.length) throw new Error(`${name}: 중복 값은 사용할 수 없습니다.`);
      value.forEach(item => validate(item, schema.items, name));
    } else if (schema.type === 'integer') {
      if (!Number.isSafeInteger(value) || value < schema.minimum || value > schema.maximum) throw new Error(`${name}: ${schema.minimum}~${schema.maximum} 사이 정수가 필요합니다.`);
    } else if (schema.type === 'string') {
      if (typeof value !== 'string' || value.length > schema.maxLength) throw new Error(`${name}: ${schema.maxLength}자 이하 문자열이 필요합니다.`);
    } else if (schema.type === 'boolean' && typeof value !== 'boolean') {
      throw new Error(`${name}: true 또는 false가 필요합니다.`);
    }
    if (schema.enum && !schema.enum.includes(value)) throw new Error(`${name}: 지원하는 값은 ${schema.enum.join(', ')}입니다.`);
  }

  async function getJson(path, params, signal) {
    const url = new URL(path, location.origin);
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timeout = setTimeout(abort, 30000);
    try {
      const response = await fetch(url, {
        method: 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: { Accept: 'application/json' }, signal: controller.signal,
      });
      if (!response.ok) throw new Error(`조회 실패 (HTTP ${response.status}). 카드 ID와 연결 상태를 확인하세요.`);
      return await response.json();
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', abort);
    }
  }

  async function register(name, title, description, inputSchema, execute) {
    try {
      await context.registerTool({
        name, title, description, inputSchema,
        annotations: { readOnlyHint: true },
        execute: async (input, options) => {
          try {
            validate(input, inputSchema);
            return await execute(input, options?.signal);
          } catch (error) {
            return { error: error.name === 'AbortError' ? '조회가 취소되었거나 시간이 초과되었습니다.' : error.message };
          }
        },
      });
    } catch (error) {
      // Registration failure must not interrupt the site's existing scripts.
      console.warn(`[Fimobook WebMCP] ${name} 등록 실패`, error);
    }
  }

  const searchSchema = objectSchema({
    query: textSchema('한 명의 선수 이름(한국어/영어), 이름 일부 또는 카드 ID. 생략하면 필터만으로 검색합니다.'),
    class_name: textSchema('클래스/시즌 이름 일부. 예: ICON. 클래스명을 부분 일치로 검색합니다.'),
    position: { ...textSchema('주 포지션 코드. include_sub_position=true이면 부 포지션도 포함합니다.'), enum: positions },
    include_sub_position: { type: 'boolean', description: '부 포지션 포함 여부. 기본 false.' },
    min_ovr: numberSchema('최소 기본 OVR'),
    max_ovr: numberSchema('최대 기본 OVR'),
    min_price: numberSchema('최소 가격(MP). 검색용 저장 가격을 사용합니다.'),
    max_price: numberSchema('최대 가격(MP). 검색용 저장 가격을 사용합니다.'),
    price_enhance: { type: 'integer', minimum: 0, maximum: 15, description: '가격 필터·정렬에 사용할 강화 단계. 기본 0. OVR에는 적용하지 않습니다.' },
    sort: { ...textSchema('정렬. 기본 recommend.'), enum: ['recommend', 'ovr_desc', 'ovr_asc', 'price_desc', 'price_asc', 'name'] },
    limit: { type: 'integer', minimum: 1, maximum: 60, description: '최대 결과 수. 기본 24. 전체 일치 건수가 아닙니다.' },
  });

  register('fimobook_search_players', '피모북 선수 검색',
    'FC모바일 선수 카드를 이름, 클래스, 포지션, OVR, MP 가격으로 검색합니다. 선수와 클래스별 cid를 찾을 때 사용하세요. 검색 가격은 저장 데이터이므로 최신 시세는 fimobook_get_player_prices로 확인하세요.',
    searchSchema, async (input, signal) => {
      for (const field of ['ovr', 'price']) {
        if (input[`min_${field}`] !== undefined && input[`max_${field}`] !== undefined && input[`min_${field}`] > input[`max_${field}`]) throw new Error(`min_${field}는 max_${field} 이하이어야 합니다.`);
      }
      const params = { limit: input.limit ?? 24, sort: input.sort ?? 'recommend' };
      const keys = { query: 'q', class_name: 'class', position: 'position', include_sub_position: 'include_sub_position', min_ovr: 'min_ovr', max_ovr: 'max_ovr', min_price: 'min_price', max_price: 'max_price', price_enhance: 'price_enhance' };
      for (const [key, param] of Object.entries(keys)) {
        if (input[key] !== undefined) params[param] = input[key];
      }
      const players = await getJson('/api/squad_players', params, signal);
      return {
        players: players.map(player => ({ ...player, url: pageUrl(`/player/${player.cid}`) })),
        returned_count: players.length, limit: params.limit,
        note: '최대 limit개의 결과입니다. 전체 일치 건수나 전체 선수 목록이 아닙니다. price는 기본 강화 가격이며 선택한 강화 가격은 priceByEnhance에서 확인하세요. 가격 단위는 MP입니다.',
      };
    });

  async function getPlayer(cid, signal) {
    const data = await getJson('/api/player_compare', { cid }, signal);
    return { ...data, url: pageUrl(`/player/${cid}`), note: '기본 카드 능력치입니다. 사용자 지정 강화·진화·스킬 효과를 추가 계산하지 않습니다. 가격은 저장 데이터이며 단위는 MP입니다.' };
  }

  register('fimobook_get_player', '피모북 선수 상세 조회',
    '카드 ID(cid)로 FC모바일 선수의 기본 능력치, 포지션, 특성, 플레이스타일과 능력치 그룹을 조회합니다. ID가 없으면 먼저 선수 검색을 사용하세요.',
    objectSchema({ cid: cidSchema }, ['cid']), (input, signal) => getPlayer(input.cid, signal));

  register('fimobook_compare_players', '피모북 선수 비교',
    '2~4개의 서로 다른 카드 ID로 선수별 기본 능력치와 그룹을 함께 조회합니다. 비교 판단에 사용할 원본 데이터이며 강화·진화 효과는 추가 계산하지 않습니다.',
    objectSchema({ cids: cidsSchema(2, 4) }, ['cids']), async (input, signal) => ({
      players: await Promise.all(input.cids.map(cid => getPlayer(cid, signal))),
      url: pageUrl('/player_compare'),
    }));

  register('fimobook_get_player_prices', '피모북 선수 가격 조회',
    '1~40개 카드 ID의 MP 가격과 강화별 priceByEnhance, 출처 source, 확인 시각 checked_at을 조회합니다. 출처와 시각으로 최신 여부를 판단하세요. 로컬 대체 가격을 실시간 가격으로 단정하지 마세요.',
    objectSchema({ cids: cidsSchema(1, 40) }, ['cids']), async (input, signal) => {
      const data = await getJson('/api/player_prices', { cids: input.cids.join(',') }, signal);
      return {
        prices: data.prices,
        missing_cids: input.cids.filter(cid => !Object.hasOwn(data.prices, String(cid))),
        note: '단위는 MP입니다. null 또는 누락된 가격은 알 수 없는 값입니다. source와 checked_at은 서버 응답 그대로입니다.',
      };
    });

  register('fimobook_get_coupons', '피모북 쿠폰 조회',
    '피모북에 공개된 최신 쿠폰 최대 5개와 서버의 만료 표시 boolExpires를 조회합니다. 쿠폰 등록을 실행하지 않으며 실제 사용 성공을 보장하지 않습니다.',
    objectSchema({}), async (_input, signal) => ({
      coupons: await getJson('/coupons/api', { dedupe: true }, signal),
      url: pageUrl('/coupons/'),
    }));
})();
