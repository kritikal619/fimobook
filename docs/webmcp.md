# 피모북 WebMCP

공통 템플릿 `templates/base.html`, `templates/v2/base.html`에서
`static/js/webmcp.js`를 로드합니다. 현재 표준의
`document.modelContext.registerTool`을 우선 사용하며, 초기 구현의
`navigator.modelContext.registerTool`도 지원합니다. 두 API가 모두 없으면
스크립트는 즉시 종료하고 기존 사이트 기능을 그대로 사용합니다.
브라우저용 AI 에이전트가 공개된 도구를 발견해 호출하는 통합입니다.
별도 MCP 서버나 사이트 내 챗봇을 만드는 기능은 아닙니다.

## 제공하는 도구

| 도구 | 입력 | 기존 데이터 경로 |
| --- | --- | --- |
| `fimobook_search_players` | `query`, `class_name`, `position`, `include_sub_position`, OVR·가격 범위, `price_enhance`, `sort`, `limit` (전부 선택) | `/api/squad_players` |
| `fimobook_get_player` | `cid` | `/api/player_compare?cid=…` |
| `fimobook_compare_players` | 서로 다른 `cids` 2~4개 | 카드별 `/api/player_compare?cid=…` |
| `fimobook_get_player_prices` | 서로 다른 `cids` 1~40개 | `/api/player_prices?cids=…` |
| `fimobook_get_coupons` | `{}` | `/coupons/api?dedupe=true` |

검색은 기본 24개, 최대 60개까지만 반환합니다. `returned_count`는
전체 일치 건수가 아닙니다. `position`은 기존 필터의 주 포지션 검색이며
`include_sub_position`으로 부 포지션을 포함할 수 있습니다.
`class_name`은 클래스 이름의 부분 일치입니다.

가격 단위는 MP입니다. 검색의 가격 필터와 정렬은 저장 데이터의
선택한 강화 단계(0~15)를 사용하지만, 응답의 `price` 필드는 기존 API의
기본 강화 가격입니다. 선택한 강화 가격은 `priceByEnhance`를 사용합니다.
강화 선택으로 OVR을 추가 계산하지 않습니다.
가격 조회는 기존 실시간 조회 및 로컬 대체 동작을 사용하며
`source`, `checked_at`을 그대로 반환합니다. 누락 카드 ID는
`missing_cids`로 반환하고 다른 선수의 값으로 대체하지 않습니다.

상세·비교는 기본 카드 능력치이며 사용자 지정 강화·진화·스킬 효과를
추가 계산하지 않습니다. 쿠폰은 공개 API와 동일하게 최대 5개이며
`boolExpires`는 서버의 만료 표시입니다. 실제 등록 성공을 보장하지 않습니다.

모든 도구는 기존 공개 GET 경로를 호출하고 `readOnlyHint`를 제공합니다.
입력 형식과 범위를 실행 시에도 확인합니다. 조회 요청은 취소 신호를
전달하고 30초 후 종료합니다. 도구 등록 실패는 기존 화면의 스크립트
실행을 중단하지 않습니다. 외부 라이브러리나 API 키는 추가하지 않았습니다.

## 지원 브라우저에서 확인하는 방법

지원하는 브라우저에서 로컬 피모북 페이지를 연 뒤 개발자 도구 콘솔에서:

```javascript
const context = document.modelContext || navigator.modelContext;
const tools = await context.getTools();
const search = tools.find(tool => tool.name === 'fimobook_search_players');
const result = await context.executeTool(search, { query: '손흥민', limit: 3 });
console.log(result);
```

`getTools`/`executeTool`은 현재 API 기준입니다. 초기 브라우저 구현은
도구 확인 방식이 다를 수 있으므로 브라우저의 WebMCP Inspector를 사용합니다.
지원하지 않는 브라우저에서는 `context`가 없으며 도구가 등록되지 않습니다.

2026-10-02 사용자의 검증·배포 요청에 따라 확인했습니다.

- `node --check static/js/webmcp.js`: 문법 검사 통과.
- `node tests/test_webmcp.cjs`: 등록, 초기 API 호환, 미지원 브라우저,
  필터 매핑, 잘못된 입력, 중복 ID, 누락 가격, HTTP 오류, 조회 취소 검사 통과.
- `node tests/test_webmcp.cjs --live`: 도구 콜백 5개에서 실제 공개 API 호출 통과.
- Codex 내장 브라우저의 실제 WebMCP 도구 검색·호출로 도구 5개 모두 확인.
  손흥민 카드 2개 검색, 카드 상세, 두 카드 비교, 실시간 가격, 쿠폰 5개 조회 성공.
- 공개 V2 페이지에서도 도구 5개 발견 및 선수 검색 호출 성공.

운영 서버에는 `static/js/webmcp.js`, `templates/base.html`,
`templates/v2/base.html`의 WebMCP 추가분만 반영했습니다.
운영 V2 템플릿은 로컬과 다른 버전이므로 운영 원본에 스크립트 구문만
추가했고, 그 템플릿의 `v2_url_for`를 사용했습니다.
기존 파일 권한을 유지하고 `fimobook.service`를 재시작했습니다.
공개 홈과 V2 페이지 HTTP 200, 실제 스크립트 바이트 일치, 서비스 `active`,
재시작 이후 오류 관련 로그 0개를 확인했습니다.

참고: [WebMCP 명세](https://webmachinelearning.github.io/webmcp/),
[Chrome Imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api).
