import { useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import type { ContractView } from "../lib/types";
import { Button, Sheet, useToast } from "./ui";

interface Clause { id: string; title: string; preview: string; caution: string | null; common: boolean }

function Switch({ on, onClick, label, testid, disabled }: { on: boolean; onClick: () => void; label: string; testid?: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} data-testid={testid} onClick={onClick} disabled={disabled}
      className={`relative h-[30px] w-[50px] shrink-0 rounded-full transition-colors duration-200 disabled:opacity-40 ${on ? "bg-toss-blue" : "bg-grey-200"}`}>
      <span className={`absolute top-[3px] left-[3px] h-6 w-6 rounded-full bg-white shadow transition-transform duration-200 ${on ? "translate-x-5" : ""}`} />
    </button>
  );
}

/** 특약·옵션: 계약 종류별 추천 특약을 켜고 끄거나, 직접 쓴 특약을 추가한다. 작성자(A)만 바꿀 수 있다. */
export function ClausePanel({ c, canEdit, beforeChange, onChanged }: {
  c: ContractView; canEdit: boolean; beforeChange: () => Promise<boolean>; onChanged: () => Promise<void> | void;
}) {
  const toast = useToast();
  const [list, setList] = useState<Clause[]>([]);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ library: string[]; custom: string[] } | null>(null);
  const selected = c.payload?.clauses ?? [];
  const custom = c.payload?.custom_clauses ?? [];
  const invited = !["DRAFT", "READY"].includes(c.status);

  useEffect(() => {
    const q = new URLSearchParams({ contract_type: c.contract_type });
    if (c.payload?.template_id) q.set("template_id", c.payload.template_id);
    api.get<{ clauses: Clause[] }>(`/api/clauses?${q}`).then((r) => setList(r.clauses)).catch(() => setList([]));
  }, [c.contract_type, c.payload?.template_id]);

  async function apply(next: { library: string[]; custom: string[] }) {
    if (invited && !pending) { setPending(next); return; }
    setPending(null);
    if (!(await beforeChange())) return;
    setBusy(true);
    try {
      await api.put(`/api/contracts/${c.id}/clauses`, next);
      if (next.custom.includes(draft.trim())) setDraft("");
      await onChanged();
      return true;
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "특약을 바꾸지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }
  const toggle = (id: string) => apply({ library: selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id], custom });
  async function addCustom() {
    const t = draft.trim();
    if (!t) return;
    await apply({ library: selected, custom: [...custom, t] });
  }

  const count = selected.length + custom.length;
  if (!canEdit) {
    if (count === 0) return null;
    const titles = list.filter((x) => selected.includes(x.id)).map((x) => x.title);
    return (
      <div data-testid="clauses-readonly" className="rounded-3xl bg-grey-50 p-5">
        <p className="text-[15px] font-semibold">들어간 특약 {count}개</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[14px] text-grey-700">
          {titles.map((t) => <li key={t}>{t}</li>)}
          {custom.map((t) => <li key={t}>{t}</li>)}
        </ul>
        <p className="mt-2 text-[13px] text-grey-500">특약 내용은 미리보기에서 확인할 수 있어요.</p>
      </div>
    );
  }

  const specific = list.filter((x) => !x.common);
  const common = list.filter((x) => x.common);
  const Item = (x: Clause) => (
    <div key={x.id} className="flex gap-3 py-3.5">
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold">{x.title}</p>
        <p className="mt-0.5 text-[13px] leading-5 text-grey-600">{x.preview}</p>
        {x.caution && <p className="mt-1.5 inline-block rounded-lg bg-[#fff4e5] px-2 py-1 text-[12px] leading-4 text-[#b45309]">{x.caution}</p>}
      </div>
      <Switch on={selected.includes(x.id)} onClick={() => toggle(x.id)} label={x.title} testid={`clause-${x.id}`} disabled={busy} />
    </div>
  );

  return (
    <section data-testid="clauses" className="rounded-3xl border border-grey-100 bg-white shadow-[0_2px_12px_rgba(0,27,55,0.05)]">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid="clauses-toggle"
        className="flex w-full items-center gap-3 px-5 py-4 text-left">
        <span aria-hidden="true" className="grid h-10 w-10 place-items-center rounded-2xl bg-[#f1efff] text-[20px]">📝</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-semibold">특약·옵션</span>
          <span className="block text-[13px] text-grey-500">{count > 0 ? `${count}개 들어가 있어요` : "필요한 조건을 계약서에 더해요"}</span>
        </span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className={`text-grey-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="border-t border-grey-100 px-5 pb-5">
          <p className="mt-3 rounded-2xl bg-grey-50 p-3 text-[13px] leading-5 text-grey-600">
            켜면 계약서의 특약사항에 조항이 들어가고, 필요한 값은 위 입력칸에 생겨요. 법에 어긋나는 특약은 효력이 없을 수 있어요.
          </p>
          {specific.length > 0 && <p className="mt-4 text-[13px] font-semibold text-grey-500">이 계약서에 자주 넣는 특약</p>}
          <div className="divide-y divide-grey-100">{specific.map(Item)}</div>
          <p className="mt-3 text-[13px] font-semibold text-grey-500">모든 계약에 쓸 수 있는 특약</p>
          <div className="divide-y divide-grey-100">{common.map(Item)}</div>

          <p className="mt-4 text-[13px] font-semibold text-grey-500">직접 쓴 특약</p>
          {custom.length > 0 && (
            <ul className="mt-2 flex flex-col gap-2" data-testid="custom-clauses">
              {custom.map((t) => (
                <li key={t} className="flex items-start gap-2 rounded-2xl bg-grey-50 px-4 py-3 text-[14px]">
                  <span className="min-w-0 flex-1">{t}</span>
                  <button type="button" disabled={busy} aria-label={`'${t}' 삭제`} onClick={() => apply({ library: selected, custom: custom.filter((x) => x !== t) })}
                    className="shrink-0 rounded-lg px-2 text-[13px] text-grey-500 active:bg-grey-100">삭제</button>
                </li>
              ))}
            </ul>
          )}
          <label htmlFor="custom-clause" className="sr-only">직접 쓴 특약</label>
          <textarea id="custom-clause" data-testid="custom-clause-input" value={draft} maxLength={300} onChange={(e) => setDraft(e.target.value)}
            placeholder="예: 반려동물 관련 비용은 을이 부담한다." rows={2}
            className="mt-2 w-full resize-none rounded-2xl border border-grey-200 px-4 py-3 text-[15px] outline-none focus:border-toss-blue" />
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[12px] text-grey-400">{draft.length} / 300 · 최대 10개</span>
            <Button size="sm" variant="secondary" full={false} onClick={addCustom} disabled={!draft.trim() || busy || custom.length >= 10} testid="add-custom-clause">특약 추가</Button>
          </div>
        </div>
      )}
      <Sheet open={!!pending} onClose={() => setPending(null)} title="특약을 바꿀까요?">
        <p className="text-grey-600">상대방을 이미 초대했어요. 특약을 바꾸면 새 버전이 만들어지고, 받은 서명이 있으면 다시 받아야 해요.</p>
        <div className="flex flex-col gap-2 py-4">
          <Button onClick={() => pending && apply(pending)} testid="confirm-clauses">바꾸기</Button>
          <Button variant="ghost" onClick={() => setPending(null)}>취소</Button>
        </div>
      </Sheet>
    </section>
  );
}
