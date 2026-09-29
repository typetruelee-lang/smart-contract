import type { ContractView, Field, FieldType } from "./types";

export const FIELD_TYPE_LABEL: Record<FieldType, string> = {
  TEXT: "짧은 글",
  NUMBER: "숫자",
  DATE: "날짜",
  PHONE: "전화번호",
  EMAIL: "이메일",
  SELECT: "선택",
  CHECKBOX: "체크",
  LONG_TEXT: "긴 글",
  SIGNATURE: "서명",
};

export const STATUS_LABEL: Record<ContractView["status"], string> = {
  DRAFT: "작성 중",
  READY: "작성 완료",
  INVITED: "상대방 참여 대기",
  SIGNING: "서명 진행 중",
  COMPLETED: "계약 완료",
  CANCELED: "취소됨",
  EXPIRED: "만료됨",
};

export const ANCHOR_LABEL: Record<string, string> = {
  NOT_REQUESTED: "기록 안 함",
  PENDING: "기록 준비 중",
  RETRY: "다시 시도 중",
  SUBMITTED: "기록 확인 중",
  CONFIRMED: "기록 완료",
  FAILED: "기록 실패",
};

export function formatKst(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function displayValue(f: Field): string {
  const v = f.value;
  if (v === null || v === undefined || v === "") return "";
  if (f.type === "NUMBER") {
    const [i, d] = String(v).split(".");
    const n = Number(i);
    return Number.isFinite(n) ? n.toLocaleString("ko-KR") + (d ? "." + d : "") : String(v);
  }
  if (f.type === "DATE") {
    const [y, m, dd] = String(v).split("-");
    return `${Number(y)}년 ${Number(m)}월 ${Number(dd)}일`;
  }
  if (f.type === "CHECKBOX") return v === true ? "☑ 예" : "☐ 아니오";
  if (f.type === "SIGNATURE") return "서명 완료";
  return String(v);
}

export function shortHash(h: string | null | undefined): string {
  if (!h) return "";
  return `${h.slice(0, 8).toUpperCase()}…${h.slice(-8).toUpperCase()}`;
}

export function won(n: number): string {
  return n.toLocaleString("ko-KR") + "원";
}

/** 본문을 {라벨} 자리표시자 기준으로 조각낸다 (React 가 이스케이프해서 렌더링). */
export function splitBody(body: string): { text?: string; label?: string }[] {
  const out: { text?: string; label?: string }[] = [];
  const re = /\{([^{}\n]{1,40})\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body))) {
    if (m.index > last) out.push({ text: body.slice(last, m.index) });
    out.push({ label: m[1].trim() });
    last = m.index + m[0].length;
  }
  if (last < body.length) out.push({ text: body.slice(last) });
  return out;
}

/** 로그인 후 이동할 주소 검증 — 같은 사이트 경로만 허용 (오픈 리다이렉트 방지) */
export function safeRedirect(next: string | null | undefined): string {
  return next && /^\/(?![/\\])[^\\]*$/.test(next) ? next : "/";
}
