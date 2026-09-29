// 실행 환경
//  - web  : 일반 브라우저 (개발/검증 페이지). 같은 도메인 /api + httpOnly 쿠키 세션.
//  - toss : 앱인토스 번들(`npm run build:ait`). 토스가 번들을 호스팅하므로 API 는 다른 도메인 →
//           Bearer 토큰(메모리 보관) + 절대 주소 VITE_API_BASE_URL 을 사용한다.
export const RUNTIME: "web" | "toss" = import.meta.env.VITE_RUNTIME === "toss" ? "toss" : "web";
export const IS_TOSS = RUNTIME === "toss";
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
export const APP_NAME = (import.meta.env.VITE_AIT_APP_NAME as string | undefined) ?? "kyeyakhaja";

let accessToken: string | null = null;
export const tokenStore = {
  get: () => accessToken,
  set: (t: string | null) => {
    accessToken = t;
  },
};
