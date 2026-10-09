# 피모북 Android TWA

이 디렉터리는 `https://fcbook.info` PWA를 Google Play용 Android App Bundle로 만드는 Bubblewrap 프로젝트다.

## 고정 식별자

- 앱 이름: 피모북
- 패키지명: `info.fcbook.app`
- 시작 주소: `https://fcbook.info/`
- Target SDK: Android 16 / API 36
- 최소 지원: Android 6 / API 23

패키지명은 Play Console에 앱을 만든 뒤 변경할 수 없다.

## 로컬 확인

JDK 17과 Android SDK 36을 준비한 뒤 아래를 실행한다.

```sh
./gradlew assembleDebug
```

생성된 디버그 APK는 `app/build/outputs/apk/debug/app-debug.apk`에 있다. 디버그 인증서가 서버의 Digital Asset Links에 없으면 주소 표시줄이 있는 Custom Tab으로 열리는 것이 정상이다.

## Play 제출 빌드

1. Play Console에서 새 앱을 만들고 패키지명이 `info.fcbook.app`인지 확인한다.
2. Play App Signing을 사용한다.
3. 출시용 업로드 키는 `android.keystore`, 별칭은 `fimobook`이다. 비밀번호는 이 Mac 로그인 키체인의 `fimobook-android-upload-keystore` 항목에 저장돼 있다.
4. Bubblewrap CLI 1.25.0 이상에서 `bubblewrap build`를 실행해 AAB를 만든다.
5. Play Console의 **앱 서명 키 인증서** SHA-256 지문을 `.well-known/assetlinks.json`에 추가하고 웹사이트에 배포한다. 업로드 키 지문과 앱 서명 키 지문은 서로 다를 수 있다.
6. `https://fcbook.info/.well-known/assetlinks.json`이 리디렉션 없이 JSON으로 열리는지 확인한 뒤 내부 테스트 트랙에 AAB를 업로드한다.

키스토어와 비밀번호는 Git에 커밋하지 않는다.

업로드 키 SHA-256 지문은 `42:4D:31:E2:EE:78:B0:79:53:C9:6B:65:18:80:64:27:0C:CD:B5:72:1B:D9:48:2D:7F:98:6E:B4:74:88:29:13`이다. Play App Signing을 켜면 Play Console에 표시되는 **앱 서명 키 인증서** 지문도 웹사이트의 Digital Asset Links에 추가해야 한다.

Play 앱 서명 키 SHA-256 지문은 `7B:B3:AF:3D:9D:B7:B6:47:9D:56:AA:D7:41:FD:DE:21:33:DC:8C:E4:37:5E:59:40:39:CA:3B:73:04:49:C5:D6`이며 Digital Asset Links에 추가되어 있다.

## 아이콘과 첫 실행

- 일반 PWA 아이콘과 maskable 아이콘을 분리한다. maskable 아이콘은 Android 안전영역 안에 로고가 들어가도록 충분한 흰 여백을 유지한다.
- Android 8 이상은 `mipmap-anydpi-v26/ic_launcher.xml`의 적응형 아이콘을 사용하고, 이전 버전은 각 density의 `ic_launcher.png`를 사용한다.
- 로컬 APK는 업로드 키 지문, Play에서 받은 APK는 Play 앱 서명 키 지문으로 Digital Asset Links가 검증된다. 둘 중 하나라도 누락되면 첫 실행이 주소 표시줄이 있는 Custom Tab으로 폴백한다.
- 아이콘을 바꾼 뒤 기존 PWA 아이콘이 남으면 홈 화면의 기존 설치본을 삭제하고 다시 설치한다.
