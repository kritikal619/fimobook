# 피모북 GA4 측정 계획

기준 버전: `2026-09-06-2`

### 2026-09-06 Google 태그 목적지 분리

- 현재 GA4 스트림 `G-J8ZL7VF352`를 과거 속성과 공유하던 태그에서 분리해 전용 Google 태그 `GT-WKPJTP28`에 재할당했다. 새 태그에는 현재 스트림 하나만 연결되어 있다.
- 사이트는 `GT-WKPJTP28`을 로드하고 같은 ID로 `config`를 한 번만 실행한다. 명시적 사용자 행동 이벤트의 `send_to`는 현재 스트림 `G-J8ZL7VF352`로 제한한다.
- 사용하지 않던 Measurement Protocol API 비밀번호와 운영 서버의 전용 비밀번호 환경 파일·systemd 연결을 제거했다. 브라우저 태그가 차단되더라도 서버 전송으로 우회하지 않는다.

### 2026-09-03 실시간 `(설정 안함)` 크롤러 제외

- GA 모바일 앱은 첫 사용자 소스가 비어 있는 활성 사용자를 `(설정 안함)`으로 표시하지만, 같은 시각의 웹 실시간 카드는 이 사용자를 소스 표의 분모에서 제외하는 차이가 있었다.
- 2026-09-03 16:48 KST 모바일 앱의 `(설정 안함)` 15명과 같은 1분에 운영 Nginx 로그에서 명시적 크롤러 16개 IP가 확인됐다. MJ12bot, Amzn-SearchBot, bingbot 등이 집중됐으며 원본 IP는 문서에 남기지 않았다.
- 확인된 크롤러 User-Agent에는 GA 태그를 렌더링하지 않는다. 실제 Android 기기명 `CUBOT`처럼 단순히 `bot` 문자열을 포함하는 정상 모바일 기기를 오탐하지 않도록 광범위한 `bot` 부분 문자열 차단은 사용하지 않는다.
- 이 변경은 이후 유입부터 적용되며, 이미 수집된 첫 사용자 소스 값은 소급 수정하지 않는다.

## 단일 Google 태그 전송

- 페이지 조회와 모든 사용자 행동 이벤트를 동일한 Google 태그의 `gtag('event', ...)` 경로로 전송한다. 모든 명시적 이벤트의 `send_to`는 기존 스트림 `G-J8ZL7VF352`이다.
- 현재 스트림 전용 Google 태그는 `GT-WKPJTP28`이다. 로더와 `config` 모두 같은 태그 ID를 사용하고, 이 태그에는 현재 GA4 스트림 하나만 연결한다.
- Google 태그가 사용자·세션 식별자, 동의, 전송을 관리한다. 별도 ID 생성·저장·조회와 Measurement Protocol 대체 전송은 없다. 호출자가 client_id/session_id/user_id를 덮어쓰지 못하도록 제거한다.
- `ga4_server.enqueue_ga4_event`는 모든 요청에 False를 반환한다. 기존 API는 유효한 구버전 요청을 204로 끝내며, 큐·백그라운드 워커·외부 전송을 시작하지 않는다. 이미 열린 구버전 페이지의 임의 ID도 더 이상 GA에 전달되지 않는다.
- 광고 차단 등으로 Google 태그 전송이 막히면 서버로 우회하지 않는다. 이 경우 수집이 누락될 수 있으며, 숫자를 높이기 위해 별도 사용자를 만들지 않는다.
- `siteMetricsEventCount`는 Google 태그 큐에 추가한 이벤트 수이지 GA가 수신했다고 보장하는 수치가 아니다. GA 수신은 실시간 보고서의 measurement_version으로 별도 확인한다.
- 검색어·토큰 등 일반 URL 쿼리는 전송하지 않는다. 유입 판별에 필요한 `utm_*`, Google 광고 클릭 ID(`gclid`, `dclid`, `gbraid`, `wbraid`)와 `srsltid`만 `page_location`에 보존한다. 기존 통계는 소급 보정되지 않고, 새 페이지/새로고침 후 최신 브라우저 코드가 적용된다.
- 회귀 검증: `node --test tests/test_site_metrics.mjs` (9개), `python3 -m unittest discover -s tests -p test_analytics_measurement.py` (11개).

공식 API: https://developers.google.com/tag-platform/gtagjs/reference#event

### 2026-09-01 유입 소스 보완

- GA 실시간 보고서에서 활성 사용자 37명, `session_start` 36건, `first_visit` 11건을 확인했고 현재 첫 사용자 소스 표에는 `(설정 안함)`이 없었다. 직전 화면에 남은 값은 수정 전 생성된 기존 사용자의 최초 유입값으로 구분한다.
- 전체 쿼리 문자열 제거가 UTM 및 광고 클릭 ID까지 제거하던 문제를 수정했다. 민감하거나 고카디널리티인 일반 쿼리는 계속 제외한다.
- ‘첫 사용자’ 유입값은 사용자 최초 생성 시 정해지므로 과거 `(설정 안함)` 값은 소급 변경되지 않는다.

### 2026-08-31 17:57 보완 배포

- 앞선 16:05 버전은 동일 식별자 조회 및 서버 202만 확인했으며, GA 사용자 결합까지 입증하지 못했다. 사용자 재확인 요청으로 단일 태그 전송으로 보완했다. 원래 75명 중 중복 사용자 수가 얼마인지는 확인되지 않았다.
- 반영 시각: 17:57:48 KST. `static/js/site-metrics.js`, `templates/_analytics.html`, `ga4_server.py` 세 파일만 배포하고 서비스를 재시작했다. 환경변수·비밀번호·데이터베이스·GA 계정 설정은 변경하지 않았다.
- 테스트 18개 통과. 공개 페이지 HTTP 200, 구버전 이벤트 API HTTP 204, 운영 서비스 active 및 재시작 후 warning 이상 로그 없음 확인. 실제 브라우저의 전송 방식은 google-tag, 버전은 2026-08-31-4.
- GA 실시간 보고서에서 새 버전 site_interaction 17건 및 page_view 28건 수신을 각각 확인했다. 서로 다른 조회 시점의 건수이며 사용자 수나 같은 사용자 연결의 증거로 해석하지 않는다. 전체 30분 사용자 집계의 검증은 보완 이후 온전한 창(18:28 이후)으로 구분해야 한다.
- 원본은 서버 `/tmp/fimobook-ga4-single-tag.704KIWQ5/`의 `site-metrics.before.js`, `analytics.before.html`, `ga4-server.before.py`에 보관했다.

### 2026-08-31 16:05 이전 배포 기록 (17:57 버전으로 대체)

- 최종 반영: 16:05:27 KST. `static/js/site-metrics.js`, `templates/_analytics.html` 두 파일만 설치하고 `fimobook.service`를 재시작했다. 파일 권한(644/664)과 소유자를 유지했다.
- JavaScript 행동 테스트 9개와 Python 렌더링·수집 테스트 9개가 모두 통과했다. 공개 페이지 HTTP 200, 공개 JavaScript와 로컬·서버 파일의 SHA-256 일치를 확인했다.
- Chrome의 `www.fcbook.info/times` 및 인앱 브라우저의 `fcbook.info/times`에서 실제 입력 후 `siteMetricsIdentityStatus=ready`를 확인했다. 검사 시 Chrome 콘솔 오류는 없었고, 서버는 해당 브라우저 이벤트 4건에 202를 반환했다. 202는 서버 큐 접수 결과이며 GA 보고서 반영 여부와는 구분한다.
- 최종 재시작 이후 확인 시점까지 HTTP 5xx와 서비스 warning 이상 로그가 없었다. GA 계정 설정, 비밀번호, 환경변수, 데이터베이스는 수정하지 않았다.
- 첫 식별자 수정(15:53 KST) 이후 기존 태그의 404를 확인하고 로더까지 수정한 16:05 KST 사이에는 새 버전 페이지의 서버 이벤트가 전송되지 않았다. 잘못된 식별자를 만들어 보내지 않는 동작으로 인한 수집 공백이며, 복구·소급 전송하지 않았다. 기존에 열려 있던 페이지는 이전 코드를 계속 실행할 수 있다.
- 원본 두 파일은 서버 `/tmp/fimobook-ga4-identity.sNQE0FQY/`의 `site-metrics.before.js`, `analytics.before.html`에 보관했다.

## 측정 목적

페이지를 오래 열어둔 시간을 성과로 오해하지 않고, 사용자가 실제로 선수를 찾고 비교하고 스쿼드를 완성하는 행동을 측정한다.

## 핵심 KPI

| KPI | 정의 | 의사결정 |
| --- | --- | --- |
| 검색 성공률 | `search_results_view` 중 `has_results=true` 비율 | 검색 데이터·동의어 보강 우선순위 |
| 검색→선수 선택률 | `name_search` 또는 `advanced_search`에서 발생한 `player_select` 사용자 ÷ 결과 페이지 사용자 | 결과 품질과 카드 정보 개선 |
| 비교 완성률 | `comparison_complete` 사용자 ÷ `player_compare` 페이지 사용자 | 비교 도구의 진입·선택 마찰 개선 |
| 세부검색 결과 도달률 | `filtered_results_view` 사용자 ÷ `advanced_filter_apply` 사용자 | 필터 오류·무결과 조건 개선 |
| 스쿼드 완성률 | `squad_complete` 사용자 ÷ `squad_maker` 페이지 사용자 | 선수 추천과 배치 UX 개선 |
| 스쿼드 저장률 | `squad_export` 사용자 ÷ `squad_maker` 페이지 사용자 | 결과물 가치와 공유 기능 판단 |

## 품질·가드레일 지표

- `qualified_engagement`: 화면이 보이고 포커스가 있으며 실제 입력 후 활성 시간이 10초 누적된 세션.
- `active_time_milestone`: 같은 조건에서 30초·120초·300초를 달성한 실제 활성 이용.
- GA4 기본 참여시간과 `active_time_milestone`을 함께 본다. 둘의 차이가 커지면 방치 탭의 영향이 큰 것으로 본다.
- `result_count=0` 비율을 이름 검색과 세부검색으로 나눠 모니터링한다.
- 관리자 계정, `/secret/*`, `/admin/*`, 로컬 개발 호스트, 옵트아웃 쿠키는 수집하지 않는다.

## 이벤트 사전

| 이벤트 | 발생 시점 | 주요 파라미터 |
| --- | --- | --- |
| `search` | 홈 이름 검색 제출 | `search_term`, `source_surface` |
| `search_results_view` | 이름 검색 결과 렌더링 | `result_count`, `has_results` |
| `advanced_filter_apply` | 세부검색 조건 제출 | `form_field_count` |
| `filtered_results_view` | 세부검색 결과 렌더링 | `result_count`, `filter_count`, `has_results` |
| `player_select` | 검색·추천·목록에서 선수 선택 | `source_surface`, `content_id`, `result_position` |
| `comparison_start` | 상세에서 비교 시작 | `content_id` |
| `comparison_player_add` | 비교 슬롯에 선수 추가 | `slot_number`, `content_id` |
| `comparison_complete` | 양쪽 비교 선수 선택 완료 | `player_count` |
| `squad_player_add` | 스쿼드 슬롯에 선수 배치 | `slot_name`, `starter_count`, `formation` |
| `squad_complete` | 선발 슬롯 전체 완성 | `starter_count`, `formation` |
| `squad_export` | 스쿼드 이미지 생성 성공 | `starter_count`, `formation` |
| `tier_vote_submit` | 티어 투표 API 성공 | `tier`, `content_id` |
| `review_form_open` | 리뷰 작성·수정 진입 | `form_mode`, `content_id` |
| `review_submit` | 리뷰 폼 제출 시도 | `form_mode`, `content_id` |
| `coupon_copy` | 쿠폰 클립보드 복사 성공 | `source_surface` |
| `coupon_notification_enable` | 쿠폰 알림 서버 설정 성공 | `notification_mode` |
| `renewal_time_search` | 갱신시간 검색 입력 후 700ms | `query_length`, `result_count` |
| `qualified_engagement` | 실제 활성 이용 10초 | `active_seconds` |
| `active_time_milestone` | 실제 활성 이용 30·120·300초 | `active_seconds` |

모든 이벤트에는 `page_type`, `content_group`, `login_state`, `measurement_version`이 자동으로 붙는다. URL은 유입 판별 파라미터만 허용해 검색어·토큰·고카디널리티 일반 파라미터가 `page_location`에 저장되지 않게 한다.

## GA4 속성 설정

다음 항목만 맞춤 정의로 등록한다. `content_id`, `search_term`, `result_position`은 값 종류가 너무 많아 보고서용 맞춤 측정기준으로 등록하지 않는다.

### 이벤트 범위 측정기준

- `page_type`
- `source_surface`
- `form_mode`
- `measurement_version`
- `formation`
- `notification_mode`

### 사용자 범위 측정기준

- `login_state`

### 이벤트 범위 측정항목

- `result_count`
- `filter_count`
- `active_seconds`
- `starter_count`

### 주요 이벤트 후보

- `comparison_complete`
- `squad_complete`
- `squad_export`
- `coupon_notification_enable`

`review_submit`, `login_submit`, `sign_up_submit`은 현재 제출 시도를 측정하므로 주요 이벤트로 지정하지 않는다. 서버 성공 응답 이벤트가 별도로 추가된 뒤 전환으로 사용한다.

## 운영 확인 절차

1. 배포 후 GA4 DebugView 또는 실시간 보고서에서 각 핵심 흐름을 한 번씩 실행한다.
2. 이벤트 이름과 파라미터가 문서와 일치하는지 확인한다.
3. 24시간 후 이벤트 보고서에서 `page_view` 외 신규 이벤트가 유입되는지 확인한다.
4. 7일 후 `qualified_engagement` 대비 GA4 기본 참여시간을 비교해 방치 탭 왜곡 정도를 판단한다.
5. 이벤트 이름이나 의미는 유지하고, 변경이 필요하면 `measurement_version`을 갱신한다.
