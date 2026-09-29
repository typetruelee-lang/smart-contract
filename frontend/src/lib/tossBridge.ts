// TossBridge — Apps in Toss SDK 호출을 한 곳에 모은다.
//
// 개발/브라우저: mock 구현 (테스트 계정 선택, 모의 결제 시트, navigator.share 대체)
// 토스 앱 안(WebView): @apps-in-toss/web-framework 의 appLogin / 인앱결제 / 공유를 사용한다.
//   실제 SDK 연결은 TOSS_SUBMISSION_CHECKLIST.md 의 "SDK 연결" 단계를 따른다.
//   (SDK 패키지는 앱인토스 콘솔 앱 등록 후 granite 설정과 함께 추가한다)

export interface LoginResult {
  authorizationCode: string;
  referrer: "DEFAULT" | "SANDBOX";
}

export interface TossBridge {
  name: "mock" | "apps-in-toss";
  isInToss: boolean;
  appLogin(testUser?: string): Promise<LoginResult>;
  share(title: string, url: string): Promise<"shared" | "copied">;
  closeView(): void;
}

type AitSdk = {
  appLogin: () => Promise<LoginResult>;
  share?: (opts: { message: string }) => Promise<void>;
  closeView?: () => void;
};

declare global {
  interface Window {
    __APPS_IN_TOSS__?: AitSdk; // 토스 앱 WebView 가 주입 (SDK 연결 시)
  }
}

async function copy(url: string): Promise<"copied"> {
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  return "copied";
}

const mockBridge: TossBridge = {
  name: "mock",
  isInToss: false,
  async appLogin(testUser = "hong") {
    return { authorizationCode: `mock-code-${testUser}`, referrer: "SANDBOX" };
  },
  async share(title, url) {
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return "shared";
      } catch {
        /* 취소 → 복사 */
      }
    }
    return copy(url);
  },
  closeView() {
    window.history.back();
  },
};

function realBridge(sdk: AitSdk): TossBridge {
  return {
    name: "apps-in-toss",
    isInToss: true,
    appLogin: () => sdk.appLogin(),
    async share(title, url) {
      if (sdk.share) {
        await sdk.share({ message: `${title}\n${url}` });
        return "shared";
      }
      return copy(url);
    },
    closeView: () => sdk.closeView?.(),
  };
}

export function getBridge(): TossBridge {
  return typeof window !== "undefined" && window.__APPS_IN_TOSS__ ? realBridge(window.__APPS_IN_TOSS__) : mockBridge;
}
