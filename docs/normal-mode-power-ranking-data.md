# 일반모드 파워랭킹 데이터

데이터 파일: `static/data/normal-mode-power-ranking.json` (version 3).

최신 `meta`, `players`를 루트에 유지하고, 날짜별 동일 스키마를 `editions`에 저장합니다.
화면은 기본적으로 최신 날짜를 보여 줍니다. TOP 1–50, 후반 TOP 51–100, 통합을 선택할 수 있습니다.

`meta.rank_ranges`는 범위별 스쿼드 수입니다. `slot_count`는 실제 배치 수입니다.
순위표 닉네임과 연결되지 않은 사용자는 `unknown_rank_users`와 `notice`에 표시합니다.

`players`의 집계 단위는 실제 배치 포지션 + 클래스 + 선수 pid입니다.

- `counts.top_1_50`, `counts.top_51_100`: 범위별 사용 인원.
- `users`: `{rank, name, range, source_index}`. 순위 미확인은 rank=null.
- `cid`: 대조한 대표 카드. 이터널 성장 단계는 같은 클래스로 합산.
- `class_label`, `season_abbr`, `player_name`: 표시명과 검색명.
- `art_image`: 대조한 넥슨 원본의 합성 이미지. 기존 일반 이미지 캐시보다 우선 표시.
- `card_image`, `face_image`: 원본 배경·선수 사진 URL.
- `ovr`: 대표 CID의 기본 OVR. 화면에는 강화·진화 OVR과 혼동하지 않도록 표시하지 않음.

과거 데이터에 users가 없으면 ‘사용 랭커 원자료 없음’을 표시합니다.
사용 인원을 닉네임 없이 만들어 넣지 않습니다.

작업 흐름과 재생성 명령은 [power-ranking-review.md](power-ranking-review.md)에 있습니다.
기존 `build_normal_mode_power_ranking.py`는 과거 글의 텍스트 요약용이며,
원본 스쿼드 대조 결과를 갱신할 때는 `import_verified_power_ranking.py`를 사용하세요.
