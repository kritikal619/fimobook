importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js");

const firebaseConfig = {{ firebase_config | tojson }};

if (firebaseConfig && Object.keys(firebaseConfig).length) {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();

  messaging.onBackgroundMessage((payload) => {
    const notification = payload.notification || {};
    const title = notification.title || "FC모바일 쿠폰";
    const body = notification.body || "새 쿠폰이 도착했습니다.";
    self.registration.showNotification(title, {
      body,
      icon: "/static/favicon.ico",
    });
  });
}
