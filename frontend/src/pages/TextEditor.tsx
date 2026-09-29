import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ContractPreview, EditPreviewToggle, FieldSheet, newField } from "../components/contract";
import { Badge, BottomCTA, Button, Card, ErrorView, Loading, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { FIELD_TYPE_LABEL } from "../lib/format";
import type { ContractView, Field, Suggestion } from "../lib/types";

const PLACEHOLDER = `예)
금전소비대차계약서

대여금액: __________ 원
채권자: __________
채무자: __________
상환일: ____년 __월 __일
이자율: 연 ____%

빈칸은 ____ 이나 {이름} 처럼 쓰면 자동으로 찾아드려요.`;

const ASSIGNEE_LABEL = { A: "내가 입력", B: "상대방 입력", ANY: "아무나" } as const;

export default function TextEditor() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const editing = Boolean(id);
  const [loading, setLoading] = useState(editing);
  const [loadErr, setLoadErr] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [fields, setFields] = useState<Field[]>([]);
  const [sugs, setSugs] = useState<Suggestion[] | null>(null);
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [sheet, setSheet] = useState<{ field: Field; kind: "new" | "edit" | "suggestion"; sug?: Suggestion } | null>(null);
  const [busy, setBusy] = useState(false);
  const [ignored, setIgnored] = useState<Set<string>>(new Set());
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get<ContractView>(`/api/contracts/${id}`)
      .then((c) => {
        if (!c.payload) throw new ApiError(410, "PURGED", "원문이 삭제된 계약이에요.");
        if (c.my_role !== "A") throw new ApiError(403, "FORBIDDEN", "계약서를 만든 사람만 수정할 수 있어요.");
        setTitle(c.payload.title);
        setBody(c.payload.body_text);
        setFields(c.payload.fields);
      })
      .catch((e) => setLoadErr(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function findBlanks() {
    setBusy(true);
    try {
      const r = await api.post<{ suggestions: Suggestion[] }>("/api/fields/suggest", { text: body, existing_labels: fields.map((f) => f.label) });
      setSugs(r.suggestions.filter((s) => !ignored.has(s.label + "|" + s.match_text)));
      if (r.suggestions.length === 0) toast("찾은 빈칸이 없어요. ____ 나 {이름} 으로 빈칸을 표시해 보세요.");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "빈칸을 찾지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function applySugs(list: Suggestion[]) {
    if (list.length === 0) return;
    setBusy(true);
    try {
      const r = await api.post<{ text: string; fields: Field[] }>("/api/fields/apply", { text: body, suggestions: list });
      setBody(r.text);
      setFields((fs) => [...fs, ...r.fields]);
      const applied = new Set(list.map((s) => s.suggestion_id));
      // 남은 추천은 본문 위치가 바뀌었으므로 다시 분석
      const remain = (sugs ?? []).filter((s) => !applied.has(s.suggestion_id));
      if (remain.length) {
        const again = await api.post<{ suggestions: Suggestion[] }>("/api/fields/suggest", { text: r.text, existing_labels: [...fields, ...r.fields].map((f) => f.label) });
        setSugs(again.suggestions.filter((s) => !ignored.has(s.label + "|" + s.match_text)));
      } else setSugs([]);
      toast(`빈칸 ${list.length}개를 만들었어요.`);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "적용하지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  function ignore(s: Suggestion) {
    setIgnored((x) => new Set(x).add(s.label + "|" + s.match_text));
    setSugs((x) => (x ?? []).filter((y) => y.suggestion_id !== s.suggestion_id));
  }

  function saveField(f: Field) {
    if (!sheet) return;
    if (sheet.kind === "suggestion" && sheet.sug) {
      applySugs([{ ...sheet.sug, label: f.label, type: f.type, required: f.required, assignee: f.assignee, options: f.options }]);
    } else if (sheet.kind === "new") {
      const el = bodyRef.current;
      const pos = el ? el.selectionStart : body.length;
      setBody(body.slice(0, pos) + `{${f.label}}` + body.slice(pos));
      setFields((fs) => [...fs, f]);
    } else {
      const old = fields.find((x) => x.field_id === f.field_id);
      if (old && old.label !== f.label) setBody((b) => b.split(`{${old.label}}`).join(`{${f.label}}`));
      setFields((fs) => fs.map((x) => (x.field_id === f.field_id ? f : x)));
    }
    setSheet(null);
  }

  function deleteField(f: Field) {
    setBody((b) => b.split(`{${f.label}}`).join("__________"));
    setFields((fs) => fs.filter((x) => x.field_id !== f.field_id));
    setSheet(null);
  }

  async function save() {
    const t = title.trim() || body.trim().split("\n")[0]?.slice(0, 100) || "";
    if (!t) return toast("계약서 제목을 입력해 주세요.", "error");
    if (!body.trim()) return toast("계약서 내용을 입력해 주세요.", "error");
    setBusy(true);
    try {
      if (editing) {
        await api.put(`/api/contracts/${id}/content`, { title: t, body_text: body, fields, reason: "계약서 내용 수정" });
        nav(`/contracts/${id}`, { replace: true });
      } else {
        const r = await api.post<{ id: string }>("/api/contracts", { title: t, source: "TEXT", contract_type: "general", body_text: body, fields });
        nav(`/contracts/${r.id}`, { replace: true });
      }
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "저장하지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  const pageTitle = editing ? "계약서 수정" : sp.get("mode") === "paste" ? "텍스트 붙여넣기" : "새 계약서 작성";
  if (loading) return <Page title={pageTitle}><Loading /></Page>;
  if (loadErr) return <Page title={pageTitle}><ErrorView message={loadErr} /></Page>;

  const usedLabels = (except?: string) => fields.filter((f) => f.field_id !== except).map((f) => f.label);

  return (
    <Page title={pageTitle}>
      <div className="sticky top-14 z-10 -mx-5 bg-white px-5 pb-3">
        <EditPreviewToggle mode={mode} onChange={setMode} />
      </div>

      {mode === "preview" ? (
        <ContractPreview title={title || "(제목 없음)"} body={body} fields={fields} />
      ) : (
        <>
          <label className="mt-2 mb-1.5 block text-[14px] font-medium text-grey-700" htmlFor="title">계약서 제목</label>
          <input id="title" data-testid="title-input" maxLength={100} className="w-full rounded-xl border border-grey-200 px-4 py-3 text-[17px] font-semibold outline-none focus:border-toss-blue"
            placeholder="예) 금전소비대차계약서" value={title} onChange={(e) => setTitle(e.target.value)} />
          <label className="mt-5 mb-1.5 block text-[14px] font-medium text-grey-700" htmlFor="body">
            계약서 내용 {sp.get("mode") === "paste" && !editing && <span className="text-grey-500">— 복사한 내용을 붙여넣으세요</span>}
          </label>
          <textarea id="body" ref={bodyRef} data-testid="body-input" maxLength={50000} className="min-h-72 w-full rounded-xl border border-grey-200 px-4 py-3 font-mono text-[15px] leading-7 outline-none focus:border-toss-blue"
            placeholder={PLACEHOLDER} value={body} onChange={(e) => { setBody(e.target.value); setSugs(null); }} />

          <div className="mt-3 grid grid-cols-2 gap-2">
            <Button variant="secondary" size="md" onClick={findBlanks} loading={busy && sugs === null} disabled={!body.trim()} testid="find-blanks">빈칸 자동 찾기</Button>
            <Button variant="ghost" size="md" onClick={() => setSheet({ field: newField(""), kind: "new" })} testid="add-blank">+ 빈칸 직접 추가</Button>
          </div>

          {sugs && sugs.length > 0 && (
            <section className="mt-6" data-testid="suggestions">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-[17px] font-bold">빈칸 추천 {sugs.length}개</h2>
                <button className="text-[15px] font-semibold text-toss-blue" onClick={() => applySugs(sugs)} data-testid="apply-all">모두 적용</button>
              </div>
              <p className="mb-3 text-[14px] text-grey-600">확인하고 적용해 주세요. 적용하기 전에는 계약서가 바뀌지 않아요.</p>
              <div className="flex flex-col gap-2">
                {sugs.map((s) => (
                  <Card key={s.suggestion_id} className="p-4">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{s.label || "(이름 없음)"}</span>
                      <Badge tone="blue">{FIELD_TYPE_LABEL[s.type]}</Badge>
                      {s.confidence < 0.6 && <Badge tone="orange">확인 필요</Badge>}
                    </div>
                    <p className="mt-1 text-[13px] text-grey-500">{s.line}번째 줄 · “{s.match_text.slice(0, 30)}” · {s.reason}</p>
                    <div className="mt-3 flex gap-2">
                      <Button size="sm" full={false} onClick={() => applySugs([s])} testid={`apply-${s.label}`}>적용</Button>
                      <Button size="sm" variant="secondary" full={false} testid={`edit-sug-${s.label}`}
                        onClick={() => setSheet({ field: { ...newField(s.label, s.type), required: s.required, assignee: s.assignee, options: s.options }, kind: "suggestion", sug: s })}>수정 후 적용</Button>
                      <Button size="sm" variant="ghost" full={false} onClick={() => ignore(s)}>무시</Button>
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          )}

          <section className="mt-6" data-testid="field-list">
            <h2 className="mb-2 text-[17px] font-bold">빈칸 {fields.length}개</h2>
            {fields.length === 0 ? (
              <p className="text-[14px] text-grey-500">아직 빈칸이 없어요. 자동으로 찾거나 직접 추가해 보세요.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {fields.map((f) => (
                  <button key={f.field_id} data-testid={`chip-${f.label}`} onClick={() => setSheet({ field: f, kind: "edit" })}
                    className="rounded-xl bg-grey-100 px-3 py-2 text-left text-[14px] active:bg-grey-200">
                    <span className="font-semibold">{f.label}</span>
                    <span className="ml-1 text-grey-500">· {FIELD_TYPE_LABEL[f.type]} · {ASSIGNEE_LABEL[f.assignee]}{f.required ? "" : " · 선택"}</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <FieldSheet open={!!sheet} field={sheet?.field ?? null} onClose={() => setSheet(null)} onSave={saveField}
        onDelete={sheet?.kind === "edit" ? deleteField : undefined} usedLabels={usedLabels(sheet?.kind === "edit" ? sheet.field.field_id : undefined)} />

      <BottomCTA>
        <Button onClick={save} loading={busy && !!sugs} disabled={busy} testid="save-contract">{editing ? "수정 내용 저장" : "다음"}</Button>
      </BottomCTA>
    </Page>
  );
}
