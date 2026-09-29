// TossBridge — Apps in Toss SDK(@apps-in-toss/web-framework) 호출을 한 곳에 모은다.
//
// web  (개발/브라우저): mock 구현 — 테스트 계정 로그인, 화면의 모의 결제 시트, navigator.share/복사
// toss (앱인토스 번들): TossAuth.login / IAP.createOneTimePurchaseOrder / Share / File.saveBase64
import { APP_NAME, IS_TOSS } from "./runtime";

export interface LoginResult {
  authorizationCode: string;
  referrer: "DEFAULT" | "SANDBOX";
}

export interface TossBridge {
  name: "mock" | "apps-in-toss";
  isInToss: boolean;
  appLogin(testUser?: string): Promise<LoginResult>;
  share(title: string, url: string): Promise<"shared" | "copied">;
  /** 인앱결제(IAP). 운영에서는 앱인토스 SDK 결제창, 개발(mock)에서는 화면의 모의 결제 시트를 사용 */
  purchase(sku: string, orderId: string): Promise<{ result: "success" | "fail" | "cancel"; payload: Record<string, unknown> }>;
  closeView(): void;
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
  async purchase() {
    return { result: "success", payload: {} };
  },
  closeView() {
    window.history.back();
  },
};

// 앱인토스 SDK — 토스 번들(VITE_RUNTIME=toss)에서만 동적으로 불러온다
type Sdk = typeof import("@apps-in-toss/web-framework");
let sdkPromise: Promise<Sdk> | null = null;
const loadSdk = () => (sdkPromise ??= import("@apps-in-toss/web-framework"));

const tossBridge: TossBridge = {
  name: "apps-in-toss",
  isInToss: true,
  async appLogin() {
    const sdk = await loadSdk();
    return sdk.TossAuth.login();
  },
  async share(title, url) {
    const sdk = await loadSdk();
    let link = url;
    try {
      // 토스 앱에서 바로 열리는 공유 링크 (intoss:// 딥링크)
      const path = new URL(url).pathname;
      link = await sdk.Share.createLink({ path: `intoss://${APP_NAME}${path}` });
    } catch {
      /* 웹 링크 그대로 공유 */
    }
    await sdk.Share.sendMessage({ message: `${title}\n${link}` });
    return "shared";
  },
  async purchase(sku, orderId) {
    const sdk = await loadSdk();
    if (!sdk.IAP.createOneTimePurchaseOrder.isSupported()) return { result: "fail", payload: { reason: "IAP_NOT_SUPPORTED" } };
    return new Promise((resolve) => {
      sdk.IAP.createOneTimePurchaseOrder({
        options: {
          sku,
          // 상품 지급은 서버가 결제 확인 후 처리하므로 여기서는 성공 응답만 한다
          processProductGrant: () => true,
        },
        onEvent: (e) => resolve({ result: "success", payload: { iapOrderId: e.data.orderId, serverOrderId: orderId, amount: e.data.amount } }),
        onError: (err) => resolve({ result: String(err).toLowerCase().includes("cancel") ? "cancel" : "fail", payload: { error: String(err).slice(0, 200) } }),
      });
    });
  },
  closeView() {
    loadSdk().then((sdk) => sdk.closeView());
  },
};

export async function saveFileInToss(blob: Blob, filename: string) {
  const sdk = await loadSdk();
  const data = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
  if (sdk.File.saveBase64.isSupported()) return sdk.File.saveBase64({ data, fileName: filename, mimeType: blob.type || "application/pdf" });
  if (sdk.File.openPDFViewer.isSupported()) {
    await sdk.File.openPDFViewer({ data, filename });
    return;
  }
  throw new Error("이 토스 앱 버전에서는 파일 저장을 지원하지 않아요. 토스 앱을 업데이트해 주세요.");
}

export function getBridge(): TossBridge {
  return IS_TOSS ? tossBridge : mockBridge;
}
