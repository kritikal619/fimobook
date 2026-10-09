(function () {
  if (!("serviceWorker" in navigator)) return;

  // Share the controlling registration with push setup before a user taps.
  window.fimoPwaReady = navigator.serviceWorker.register("/firebase-messaging-sw.js", {
    scope: "/", updateViaCache: "none",
  });
  window.fimoPwaReady.catch(function (error) {
    window.fimoPwaReady = null;
    console.warn("피모북 서비스 워커 등록 실패", error);
  });
})();
