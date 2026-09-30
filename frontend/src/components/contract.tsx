import { useState } from "react";
import { Button, Check, Sheet } from "./ui";
import { FIELD_TYPE_LABEL, displayValue, splitBody } from "../lib/format";
import type { Field, FieldType, Role } from "../lib/types";

export const ALL_TYPES: FieldType[] = ["TEXT", "NUMBER", "DATE", "PHONE", "EMAIL", "SELECT", "CHECKBOX", "LONG_TEXT", "SIGNATURE"];

export function newField(label: string, type: FieldType = "TEXT"): Field {
  const rnd = Array.from(crypto.getRandomValues(new Uint8Array(4)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return { field_id: `f_${rnd}`, label, type, value: null, required: true, assignee: "A", page: null, position: null, options: [], validation: {} };
}

/** 계약서 미리보기 — 본문의 {라벨} 을 입력값으로 바꿔서 보여준다. (React 가 모두 이스케이프) */
export function ContractPreview({ title, body, fields, highlight }: { title: string; body: string; fields: Field[]; highlight?: Role }) {
  const byLabel = new Map(fields.map((f) => [f.label, f]));
  return (
    <article data-testid="contract-preview" className="rounded-2xl border border-grey-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-center text-[20px] font-bold">{title}</h2>
      <div className="text-[15px] leading-7 whitespace-pre-wrap text-grey-800">
        {splitBody(body.replace(new RegExp(`^\\s*${title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n`), "")).map((p, i) => {
          if (p.text !== undefined) return <span key={i}>{p.text}</span>;
          const f = byLabel.get(p.label!);
          if (!f) return <span key={i}>{`{${p.label}}`}</span>;
          const v = displayValue(f);
          const mine = highlight && (f.assignee === highlight || f.assignee === "ANY");
          if (f.type === "SIGNATURE")
            return (
              <span key={i} className={`mx-0.5 inline-block rounded-md border border-dashed px-2 text-[13px] ${f.value ? "border-ok text-ok" : "border-grey-400 text-grey-500"}`}>
                {f.value ? "✍️ 서명됨" : `${f.label}`}
              </span>
            );
          return v ? (
            <span key={i} className="mx-0.5 rounded bg-toss-blue-light px-1 font-semibold text-toss-blue-dark">{v}</span>
          ) : (
            <span key={i} className={`mx-0.5 rounded px-1 text-[14px] ${mine ? "bg-[#fff4e5] text-[#b45309]" : "bg-grey-100 text-grey-500"}`}>
              {f.label}
            </span>
          );
        })}
      </div>
    </article>
  );
}

export function FieldInput({ f, value, onChange, disabled, error }: { f: Field; value: Field["value"]; onChange: (v: Field["value"]) => void; disabled?: boolean; error?: string }) {
  const cls = `w-full rounded-xl border bg-white px-4 py-3 text-[16px] outline-none focus:border-toss-blue ${error ? "border-warn" : "border-grey-200"} disabled:bg-grey-50 disabled:text-grey-500`;
  const id = `in-${f.field_id}`;
  const label = (
    <label htmlFor={id} className="mb-1.5 flex items-center gap-1 text-[14px] font-medium text-grey-700">
      {f.label}
      {f.required && <span className="text-warn">*</span>}
      <span className="ml-auto text-[12px] text-grey-400">{FIELD_TYPE_LABEL[f.type]}</span>
    </label>
  );
  const s = value === null || value === undefined ? "" : String(value);
  let input;
  switch (f.type) {
    case "LONG_TEXT":
      input = <textarea id={id} data-testid={`input-${f.label}`} className={`${cls} min-h-28`} value={s} disabled={disabled} maxLength={2000} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "NUMBER":
      input = (
        <input id={id} data-testid={`input-${f.label}`} className={cls} inputMode="decimal" value={s} disabled={disabled} placeholder="숫자만 입력"
          onChange={(e) => onChange(e.target.value.replace(/[^\d.,]/g, ""))} />
      );
      break;
    case "DATE":
      input = <input id={id} data-testid={`input-${f.label}`} type="date" className={cls} value={s} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "PHONE":
      input = <input id={id} data-testid={`input-${f.label}`} type="tel" className={cls} value={s} disabled={disabled} placeholder="010-0000-0000" onChange={(e) => onChange(e.target.value)} />;
      break;
    case "EMAIL":
      input = <input id={id} data-testid={`input-${f.label}`} type="email" className={cls} value={s} disabled={disabled} placeholder="name@example.com" onChange={(e) => onChange(e.target.value)} />;
      break;
    case "SELECT":
      input = (
        <select id={id} data-testid={`input-${f.label}`} className={cls} value={s} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          <option value="">선택해 주세요</option>
          {f.options.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      );
      break;
    case "CHECKBOX":
      return (
        <div className="py-1">
          <Check testid={`input-${f.label}`} checked={value === true} onChange={(v) => !disabled && onChange(v)}>
            {f.label} {f.required && <span className="text-warn">*</span>}
          </Check>
          {error && <p className="mt-1 text-[13px] text-warn">{error}</p>}
        </div>
      );
    case "SIGNATURE":
      return (
        <div className="py-1">
          {label}
          <div className="rounded-xl border border-dashed border-grey-300 px-4 py-3 text-[14px] text-grey-500">{value ? "✍️ 서명 완료" : "서명 단계에서 자동으로 채워져요"}</div>
        </div>
      );
    default: {
      // 형식이 정해진 글자 칸(근로시간 09:00, 요일별 09:00~13:00 등)은 서버가 예시 값과 길이 제한을 함께 보낸다
      const example = typeof f.validation?.example === "string" ? f.validation.example : "";
      const max = typeof f.validation?.maxLength === "number" ? Math.min(f.validation.maxLength, 200) : 200;
      input = (
        <input id={id} data-testid={`input-${f.label}`} className={cls} value={s} disabled={disabled} maxLength={max}
          placeholder={example ? `예: ${example}` : undefined} onChange={(e) => onChange(e.target.value)} />
      );
    }
  }
  const interestWarning = f.type === "NUMBER" && /이자|이율/.test(f.label) && Number(String(value ?? "").replace(/,/g, "")) > 20;
  return (
    <div className="py-1">
      {label}
      {input}
      {error && <p className="mt-1 text-[13px] text-warn">{error}</p>}
      {interestWarning && (
        <p data-testid="interest-warning" className="mt-1 text-[13px] text-[#b45309]">
          이자제한법상 최고이자율(연 20%)을 넘는 부분은 효력이 없을 수 있어요. 금액과 이율을 다시 확인해 주세요.
        </p>
      )}
    </div>
  );
}

/** 빈칸 속성 편집 시트 (이름, 입력 유형, 필수, 입력하는 사람, 선택지) */
export function FieldSheet({ field, open, onClose, onSave, onDelete, usedLabels }: {
  field: Field | null; open: boolean; onClose: () => void; onSave: (f: Field) => void; onDelete?: (f: Field) => void; usedLabels: string[];
}) {
  const [draft, setDraft] = useState<Field | null>(field);
  const [opts, setOpts] = useState("");
  const [err, setErr] = useState("");
  if (field && draft?.field_id !== field.field_id) {
    setDraft(field);
    setOpts(field.options.join(", "));
    setErr("");
  }
  if (!draft) return null;
  const save = () => {
    const label = draft.label.trim();
    if (!label || /[{}<>\n]/.test(label) || label.length > 40) return setErr("이름은 1~40자, { } < > 는 쓸 수 없어요.");
    if (usedLabels.includes(label)) return setErr("같은 이름의 빈칸이 이미 있어요.");
    const options = draft.type === "SELECT" ? opts.split(",").map((s) => s.trim()).filter(Boolean) : [];
    if (draft.type === "SELECT" && options.length === 0) return setErr("선택지를 쉼표(,)로 구분해 입력해 주세요.");
    onSave({ ...draft, label, options, value: draft.type === "SIGNATURE" ? null : draft.value });
  };
  return (
    <Sheet open={open} onClose={onClose} title="빈칸 설정">
      <div className="flex max-h-[65vh] flex-col gap-4 overflow-y-auto pb-2">
        <div>
          <label className="mb-1.5 block text-[14px] font-medium text-grey-700" htmlFor="fs-label">빈칸 이름</label>
          <input id="fs-label" data-testid="field-label" className="w-full rounded-xl border border-grey-200 px-4 py-3 outline-none focus:border-toss-blue" value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
        </div>
        <div>
          <p className="mb-1.5 text-[14px] font-medium text-grey-700">입력 유형</p>
          <div className="grid grid-cols-3 gap-2">
            {ALL_TYPES.map((t) => (
              <button key={t} data-testid={`type-${t}`} onClick={() => setDraft({ ...draft, type: t })}
                className={`h-11 rounded-xl text-[14px] font-medium ${draft.type === t ? "bg-toss-blue text-white" : "bg-grey-100 text-grey-700"}`}>
                {FIELD_TYPE_LABEL[t]}
              </button>
            ))}
          </div>
        </div>
        {draft.type === "SELECT" && (
          <div>
            <label className="mb-1.5 block text-[14px] font-medium text-grey-700" htmlFor="fs-opts">선택지 (쉼표로 구분)</label>
            <input id="fs-opts" className="w-full rounded-xl border border-grey-200 px-4 py-3" value={opts} onChange={(e) => setOpts(e.target.value)} placeholder="계좌이체, 현금" />
          </div>
        )}
        <div>
          <p className="mb-1.5 text-[14px] font-medium text-grey-700">누가 입력하나요?</p>
          <div className="grid grid-cols-3 gap-2">
            {([["A", "나 (작성자)"], ["B", "상대방"], ["ANY", "아무나"]] as const).map(([k, l]) => (
              <button key={k} data-testid={`assignee-${k}`} onClick={() => setDraft({ ...draft, assignee: k })}
                className={`h-11 rounded-xl text-[14px] font-medium ${draft.assignee === k ? "bg-toss-blue text-white" : "bg-grey-100 text-grey-700"}`}>{l}</button>
            ))}
          </div>
        </div>
        <Check testid="field-required" checked={draft.required} onChange={(v) => setDraft({ ...draft, required: v })}>꼭 입력해야 해요 (필수)</Check>
        {err && <p className="text-[14px] text-warn">{err}</p>}
      </div>
      <div className="flex gap-2 py-3">
        {onDelete && <Button variant="danger" full={false} onClick={() => onDelete(draft)} testid="field-delete">삭제</Button>}
        <Button onClick={save} testid="field-save">저장</Button>
      </div>
    </Sheet>
  );
}

export function EditPreviewToggle({ mode, onChange }: { mode: "edit" | "preview"; onChange: (m: "edit" | "preview") => void }) {
  return (
    <div role="tablist" className="grid grid-cols-2 rounded-xl bg-grey-100 p-1">
      {(["edit", "preview"] as const).map((m) => (
        <button key={m} role="tab" aria-selected={mode === m} data-testid={`tab-${m}`} onClick={() => onChange(m)}
          className={`h-10 rounded-lg text-[15px] font-semibold ${mode === m ? "bg-white text-grey-900 shadow-sm" : "text-grey-500"}`}>
          {m === "edit" ? "편집" : "미리보기"}
        </button>
      ))}
    </div>
  );
}
