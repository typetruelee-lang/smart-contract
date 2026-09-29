import { type ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export function Page({ children, title, back = true, right, onBack }: { children: ReactNode; title?: string; back?: boolean; right?: ReactNode; onBack?: () => void }) {
  const nav = useNavigate();
  return (
    <div className="mx-auto flex min-h-dvh max-w-[480px] flex-col bg-white">
      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 bg-white px-2">
        {back ? (
          <button aria-label="뒤로가기" onClick={() => (onBack ? onBack() : window.history.length > 1 ? nav(-1) : nav("/"))} className="grid h-10 w-10 place-items-center rounded-full text-grey-800 active:bg-grey-100">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M15 5l-7 7 7 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        ) : (
          <div className="w-2" />
        )}
        <h1 className="flex-1 truncate text-[17px] font-semibold">{title}</h1>
        {right}
      </header>
      <main className="flex flex-1 flex-col px-5 pb-6">{children}</main>
    </div>
  );
}

type BtnProps = { children: ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "lg" | "md" | "sm"; type?: "button" | "submit"; full?: boolean; loading?: boolean; testid?: string };

export function Button({ children, onClick, disabled, variant = "primary", size = "lg", type = "button", full = true, loading, testid }: BtnProps) {
  const base = "inline-flex items-center justify-center gap-2 rounded-2xl font-semibold transition active:scale-[0.98] disabled:opacity-40";
  const v = {
    primary: "bg-toss-blue text-white active:bg-toss-blue-dark",
    secondary: "bg-toss-blue-light text-toss-blue",
    ghost: "bg-grey-100 text-grey-700",
    danger: "bg-[#fff0f1] text-warn",
  }[variant];
  const s = { lg: "h-14 px-5 text-[17px]", md: "h-12 px-4 text-[16px]", sm: "h-9 px-3 text-[14px] rounded-xl" }[size];
  return (
    <button data-testid={testid} type={type} onClick={onClick} disabled={disabled || loading} className={`${base} ${v} ${s} ${full ? "w-full" : ""}`}>
      {loading ? <Spinner small /> : null}
      {children}
    </button>
  );
}

export function BottomCTA({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="h-24" />
      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 mx-auto max-w-[480px] bg-gradient-to-t from-white via-white to-white/0 px-5 pt-6">
        <div className="flex flex-col gap-2">{children}</div>
      </div>
    </>
  );
}

export function Card({ children, className = "", onClick, testid }: { children: ReactNode; className?: string; onClick?: () => void; testid?: string }) {
  const C = onClick ? "button" : "div";
  return (
    <C data-testid={testid} onClick={onClick} className={`w-full rounded-2xl bg-grey-50 p-5 text-left ${onClick ? "active:bg-grey-100" : ""} ${className}`}>
      {children}
    </C>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  return <span role="status" aria-label="불러오는 중" className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${small ? "h-4 w-4" : "h-8 w-8 text-toss-blue"}`} />;
}

export function Loading({ label = "불러오는 중이에요" }: { label?: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-24 text-grey-600">
      <Spinner />
      <p>{label}</p>
    </div>
  );
}

export function ErrorView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const nav = useNavigate();
  return (
    <div data-testid="error-view" className="flex flex-1 flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="text-5xl">😢</div>
      <p className="text-[18px] font-semibold">문제가 생겼어요</p>
      <p className="text-grey-600">{message}</p>
      <div className="mt-4 flex w-full max-w-[280px] flex-col gap-2">
        {onRetry && <Button onClick={onRetry}>다시 시도</Button>}
        <Button variant="ghost" onClick={() => nav("/")}>처음으로</Button>
      </div>
    </div>
  );
}

export function Badge({ children, tone = "grey" }: { children: ReactNode; tone?: "grey" | "blue" | "green" | "orange" | "red" }) {
  const t = { grey: "bg-grey-100 text-grey-700", blue: "bg-toss-blue-light text-toss-blue", green: "bg-[#e5f8ee] text-ok", orange: "bg-[#fff4e5] text-[#d97706]", red: "bg-[#fff0f1] text-warn" }[tone];
  return <span className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[13px] font-semibold ${t}`}>{children}</span>;
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="safe-bottom w-full max-w-[480px] rounded-t-3xl bg-white px-5 pt-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-[20px] font-bold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Row({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <span className="shrink-0 text-grey-600">{label}</span>
      <span className={`text-right ${mono ? "font-mono text-[13px] break-all" : "font-medium"}`}>{children}</span>
    </div>
  );
}

export function Check({ checked, onChange, children, testid }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; testid?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2.5">
      <input data-testid={testid} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 transition peer-focus-visible:ring-2 peer-focus-visible:ring-toss-blue ${checked ? "border-toss-blue bg-toss-blue text-white" : "border-grey-300"}`}>
        {checked && <svg width="14" height="14" viewBox="0 0 24 24"><path d="M5 12l5 5 9-10" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      </span>
      <span className="text-[16px] leading-6">{children}</span>
    </label>
  );
}

// ---------------- 토스트 ----------------
type Toast = { id: number; text: string; tone: "info" | "error" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems([{ id, text, tone }]); // 한 번에 하나만 (겹쳐 쌓이지 않게)
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), tone === "error" ? 3500 : 2200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-28 z-[60] flex flex-col items-center gap-2 px-5">
        {items.map((t) => (
          <div key={t.id} role="alert" className={`max-w-[440px] rounded-2xl px-4 py-3 text-[15px] text-white shadow-lg ${t.tone === "error" ? "bg-[#e5323f]" : "bg-grey-900/90"}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[18px] font-bold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}
