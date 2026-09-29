// 앱인토스 배포 설정 — `npm run build:ait` 가 dist/ 를 <appName>.ait 로 묶는다.
// appName 은 앱인토스 콘솔에 등록한 앱 이름(케밥-케이스)과 같아야 한다. (FINAL_USER_ACTIONS.md 참조)
import { defineConfig } from "@apps-in-toss/web-framework/config";

export default defineConfig({
  appName: "kyeyakhaja",
  brand: { primaryColor: "#3182F6" },
  permissions: [{ name: "clipboard", access: "write" }],
  navigationBar: { withBackButton: true, withHomeButton: true, withTitle: true, theme: "light" },
  webView: { allowsBackForwardNavigationGestures: true, pullToRefreshEnabled: false, bounces: false },
  webBundleDir: "dist",
});
