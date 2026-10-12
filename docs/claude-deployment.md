# Claude Code 배포 안내 및 2026-10-09 SSH 장애 인계

## 복구 결과

사용자가 Mac 잠금을 해제한 뒤 기존 SSH 별칭 인증과 서비스 상태 확인이
성공했다. 키 파일 읽기 정지의 macOS 내부 원인은 확정하지 않았다.
재발 가능성을 줄이기 위해 기존 키를 같은 사용자 `~/.ssh/fimobook-prod.pem`에
권한 600으로 보관하고, SSH 설정에서 해당 별칭의 `IdentityFile`만 바꿨다.
설정 백업은 `~/.ssh/config.before-claude-deploy-20261009`이다. 원래 키는 유지했다.
새 키 경로로 접속하여 서비스 `active`를 확인했다. 잠긴 상태에서 재현 검사는 하지 않았다.

Codex가 미배포 변경 11개를 운영 원본에 선별 적용하고 배포했다.
아래 "확인한 사실"은 복구 전 진단 기록이며, 최종 결과는
`artifacts/claude-deploy-20261009/deployment-report.md`를 참고한다.
Claude UI 메시지 전송은 자동 승인 검토가 명시적 전송 승인 부족으로 거절하여
실행하지 않았다. 거절을 다른 도구로 우회하지 않았다.

## 확인한 사실

- Claude 작업 기록의 배포 요청은 가격 조회 동시 처리 수정과 검색·갱신시간·수수료 UI 변경이다.
- 서버 22번 TCP 연결과 SSH 배너 응답은 즉시 성공했다.
- 개인키 파일을 사용하지 않은 진단은 서버 호스트키 검증, 키 교환, 공개키 인증 요청까지 성공했다.
  인증 실패는 진단에 키를 제공하지 않았기 때문에 예상된 결과다.
- 기존 개인키 경로를 사용하면 `Connection established` 뒤 18~20초 전체 제한까지 정지했다.
  Python으로 같은 파일을 읽는 진단도 6초 제한까지 정지했다. 파일 stat은 성공했다.
- `IPQoS=none`과 전역 SSH 설정 제외는 증상을 해결하지 못했다.
- SSH 에이전트에 등록된 키는 없었다.
- Mac이 잠겨 있어 Claude UI에 진단 결과를 직접 전달할 수 없었다.
- 원격 셸 인증에 성공하지 못했으므로 운영 파일 업로드·서비스 재시작은 하지 않았다.

이 증거는 로컬 개인키 파일 접근 문제를 가리킨다. macOS 개인정보 보호 승인,
화면 잠금, 파일 제공자 등의 구체적 원인은 아직 확정하지 않았다. AWS 재부팅,
보안 그룹 변경, sshd 재설정으로 해결된다고 주장하지 않는다.

## 먼저 할 일

1. 사용자에게 Mac 잠금을 해제하도록 요청한다. 필요한 macOS 접근 승인 창이 있는지 확인한다.
2. 다음 명령으로 기존 SSH 설정 그대로 인증과 서비스 상태를 확인한다.
3. 실패하면 정확한 출력과 정지 지점을 보고한다. 개인키는 출력하지 않는다.
   파일 접근 권한 거절을 우회하거나 전체 디스크 접근 권한을 임의로 켜지 않는다.
4. 현재 별칭은 이미 `~/.ssh/fimobook-prod.pem`을 사용한다. 키 문제 발생 시
   파일 경로와 소유권·권한을 확인한다. 저장소나 `/tmp`에 개인키를 복사하지 않는다.
   원격 인증키·계정 권한은 별도 요청 없이 변경하지 않는다.

```sh
python3 - <<'PY'
import subprocess
command = [
    'ssh', '-v', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
    '-o', 'ConnectionAttempts=1', 'fimobook-prod',
    'systemctl is-active fimobook.service',
]
try:
    result = subprocess.run(command, timeout=20)
    raise SystemExit(result.returncode)
except subprocess.TimeoutExpired:
    print('SSH 전체 실행시간 20초 초과. 로컬 키 파일 접근과 마지막 로그를 확인하세요.')
    raise SystemExit(124)
PY
```

`BatchMode`는 대화형 암호 입력을 막는다. `ConnectTimeout` 외에 전체 실행시간
제한을 둬서 로컬 키 읽기 정지가 끝없이 남지 않게 한다. 위 subprocess는 제한이
지나면 자신이 시작한 SSH 프로세스를 종료한다.

## 인증 복구 후 배포 순서

1. `AGENTS.md`를 읽는다. 사용자 요청의 정확한 파일 목록과 변경을 확인한다.
2. 운영의 해당 원본을 내려받아 로컬과 비교한다. 로컬 커밋에 이전 작업이 섞여
   있으므로 커밋 전체나 `app.py` 전체를 운영에 그대로 덮어쓰지 않는다.
3. 운영 원본에 이번 변경만 적용한 후보와 파일별 diff를 작업 산출물에 준비한다.
   사용자가 테스트를 요청하지 않았다면 테스트 실행·추가는 하지 않는다.
4. SSH 별칭으로 서버에 고유 staging 디렉터리를 만든다:
   `ssh fimobook-prod 'mktemp -d /tmp/fimobook-deploy-XXXXXXXX'`.
   이번 후보 파일만 그 디렉터리에 업로드한다. 운영 원본 백업과 SHA256 목록을 남긴다.
5. 기존 파일의 uid/gid/mode를 기록하고 `sudo`로 정확한 앱 경로에 설치한다.
   기존 root 소유 파일은 ubuntu 권한만으로 소유권 보존이 실패할 수 있다.
   파일별 기존 권한·소유권을 보존하고 설치 후 SHA256을 후보와 비교한다.
6. Python 또는 템플릿 변경 시 `sudo systemctl reload fimobook.service`를 쓴다.
   gunicorn이 소켓을 유지한 채 워커만 교체해 502가 나지 않는다
   (`fimobook.service.d/zz-reload.conf`에 `ExecReload=kill -HUP`). 환경변수나
   gunicorn 옵션을 바꾼 경우에만 `restart`를 쓴다.
   2026-10-11부터 소켓은 `fimobook.socket`(systemd 소켓 활성화)이 쥐고 있어 `restart`
   중에도 요청이 대기열에 쌓이고 502가 나지 않는다. 롤백은 `fimobook.socket`을
   중지·비활성화하고 `fimobook.service.d/zz-socket-activation.conf`를 지운 뒤
   `daemon-reload`, 서비스를 시작한다(원본 백업: 서버 `/tmp/fimobook-systemd-backup-*`).
   `systemctl is-active fimobook.service`와 이번 재시작 이후 journal을 확인한다.
7. `https://fcbook.info`의 영향받는 페이지와 새 정적 자산 버전·동작을 확인한다.
   기존 봇 차단 때문에 curl의 403만으로 장애라고 판단하지 않는다. 정상 브라우저로 확인한다.
8. 실제 설치 파일, 백업 위치, 해시·권한·서비스·공개 페이지 확인 결과를 보고한다.
   실패한 단계는 명시하고 파괴적 자동 롤백을 하지 않는다.

선수 JSON 갱신은 `AGENTS.md`의 서버 이미지 완전성 검증을 먼저 수행해야 한다.
`.env`, DB, 업로드, venv, 생성 데이터, 계정 설정을 이번 UI/가격 배포에 포함하지 않는다.

## 이번 미배포 작업의 시작 목록

Claude의 마지막 인계 기준이며 실제 코드와 운영 원본을 다시 비교해야 한다:

- 가격 조회: `app.py`의 가격 조회 부분, `static/js/live-prices.js`, `templates/base.html`
- UI: `templates/times.html`, `templates/market_fee_calculator.html`, `templates/traits_selection.html`
- CSS: `static/css/site-header.css`, `static/css/times-workspace.css`, `static/css/detail-search-workspace.css`
- JS: `static/js/times-workspace.js`, `static/js/detail-search-workspace.js`

2026-10-09 오전 PWA 배포 기록은 `artifacts/push-pwa-20261009/deployment-report.md`에 있다.
그 배포와 이번 Claude 작업을 혼동하지 않는다. 오전 배포의 운영 파일도 이후에
바뀌었을 수 있으므로 현재 운영 원본을 다시 받아야 한다.
