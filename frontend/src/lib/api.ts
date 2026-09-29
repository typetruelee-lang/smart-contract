// API 클라이언트 — web: httpOnly 세션 쿠키 + CSRF(double-submit) / toss: Bearer 토큰
import { API_BASE, IS_TOSS, tokenStore } from "./runtime";

export class ApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;
  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)kz_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

type Listener = (e: ApiError) => void;
const authListeners = new Set<Listener>();
export function onAuthError(fn: Listener) {
  authListeners.add(fn);
  return () => authListeners.delete(fn);
}

async function request<T>(method: string, url: string, body?: unknown, opts: { raw?: boolean; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (opts.form) {
    payload = opts.form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (IS_TOSS) {
    const t = tokenStore.get();
    if (t) headers.Authorization = `Bearer ${t}`;
    headers["X-Auth-Mode"] = "token";
  } else if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  let res: Response;
  try {
    res = await fetch(API_BASE + url, { method, headers, body: payload, credentials: IS_TOSS ? "omit" : "same-origin" });
  } catch {
    throw new ApiError(0, "NETWORK", "인터넷 연결을 확인해 주세요.");
  }
  if (!res.ok) {
    let detail: { code?: string; message?: string; [k: string]: unknown } = {};
    try {
      detail = (await res.json()).detail ?? {};
    } catch {
      /* not json */
    }
    const err = new ApiError(res.status, detail.code ?? `HTTP_${res.status}`, detail.message ?? "잠시 후 다시 시도해 주세요.", detail);
    if (res.status === 401) authListeners.forEach((fn) => fn(err));
    throw err;
  }
  if (opts.raw) return (await res.blob()) as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T>(url: string, body?: unknown) => request<T>("PUT", url, body ?? {}),
  upload: <T>(url: string, form: FormData) => request<T>("POST", url, undefined, { form }),
  blob: (url: string) => request<Blob>("GET", url, undefined, { raw: true }),
};

export async function downloadFile(url: string, filename: string) {
  const blob = await api.blob(url);
  if (IS_TOSS) {
    // 토스 WebView 는 <a download> 가 동작하지 않을 수 있어 SDK 파일 저장을 사용
    const { saveFileInToss } = await import("./tossBridge");
    return saveFileInToss(blob, filename);
  }
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}
