# Fimobook — Claude Code 운영 지침

작업 전에 이 프로젝트의 `AGENTS.md`를 읽고 따른다. 해당 파일의 배포,
Git 안전, 선수 이미지 검증 규칙은 Claude Code에도 동일하게 적용한다.
테스트 실행·추가는 사용자가 요청했을 때만 한다.

## 운영 배포

- SSH 별칭: `fimobook-prod`
- 앱 경로: `/home/ubuntu/fimobook`
- 서비스: `fimobook.service`
- 공개 사이트: `https://fcbook.info`
- 자세한 절차와 SSH 정지 진단: `docs/claude-deployment.md`

사용자의 서버 배포 요청과 GitHub 동기화 요청을 구분한다. 서버 배포를 위해
Git push나 전체 디렉터리 동기화를 할 필요는 없다. 로컬과 운영 소스가 다르므로
현재 작업의 변경만 운영 원본에 적용한다. 특히 `app.py`를 통째로 덮어쓰지 않는다.

## SSH가 멈추면

2026-10-09 복구 완료: 기존 개인키를 같은 사용자의 `~/.ssh/fimobook-prod.pem`
(권한 600)에 보관하고, `fimobook-prod`의 `IdentityFile`만 그 경로로 변경했다.
기존 별칭으로 인증 및 서비스 `active` 확인에 성공했다. 키 내용을 출력하거나
프로젝트에 복사하지 않는다. 이 경로를 다시 `Documents`로 되돌리지 않는다.
배포 결과는 `artifacts/claude-deploy-20261009/deployment-report.md`를 참고한다.

2026-10-09 진단에서는 서버의 SSH 배너와 키 교환이 정상인데, 로컬
`Documents/key`의 기존 개인키 파일 읽기가 멈췄다. 따라서 `Connection
established` 뒤 로그가 멈춘 것만으로 서버 sshd 장애나 AWS 문제라고 단정하지 않는다.
화면 잠금과 macOS 파일 접근 상태를 사용자가 확인하도록 안내한다.
권한 거절을 다른 터미널이나 도구로 우회하지 않는다.

SSH 진단은 `docs/claude-deployment.md`의 전체 실행시간 제한 예제를 사용한다.
`ConnectTimeout`만으로 로컬 파일 읽기 정지를 제한할 수는 없었다.
`pkill -f ssh` 또는 `pkill -f fimobook-prod`처럼 다른 작업의 연결까지 죽이는
명령을 사용하지 않는다. 개인키 내용은 출력·로그·저장소에 남기지 않는다.
