import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FieldSheet, newField } from "../components/contract";
import { PdfPage, usePdf } from "../components/PdfCanvas";
import { Badge, BottomCTA, Button, Card, Loading, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { FIELD_TYPE_LABEL } from "../lib/format";
import type { Field, Position, PositionSuggestion, Suggestion } from "../lib/types";

interface Analysis {
  pages: { width: number; height: number; ocr: boolean; text: string }[];
  text: string;
  ocr_used: boolean;
  suggestions: Suggestion[];
  position_suggestions: PositionSuggestion[];
}

type Drag = { kind: "draw" | "move" | "resize"; page: number; startX: number; startY: number; fieldId?: string; orig?: Position; rect?: DOMRect };

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));

export default function PdfEditor() {
  const nav = useNavigate();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [buf, setBuf] = useState<ArrayBuffer | null>(null);
  const [an, setAn] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [fields, setFields] = useState<Field[]>([]);
  const [posSugs, setPosSugs] = useState<PositionSuggestion[]>([]);
  const [textSugs, setTextSugs] = useState<Suggestion[]>([]);
  const [addMode, setAddMode] = useState<null | { label: string; type: Field["type"] }>(null);
  const [draft, setDraft] = useState<{ page: number; pos: Position } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [sheet, setSheet] = useState<{ field: Field; isNew: boolean } | null>(null);
  const drag = useRef<Drag | null>(null);
  const { doc, err } = usePdf(buf);

  async function onFile(f: File | undefined) {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) return toast("PDF 파일(.pdf)만 올릴 수 있어요.", "error");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", f);
      const r = await api.upload<Analysis>("/api/uploads/pdf/analyze", form);
      setFile(f);
      setBuf(await f.arrayBuffer());
      setAn(r);
      setPosSugs(r.position_suggestions);
      setTextSugs(r.ocr_used ? r.suggestions : []);
      const firstLine = r.text.split("\n").map((s) => s.trim()).find(Boolean) ?? "";
      setTitle(firstLine.slice(0, 60) || f.name.replace(/\.pdf$/i, ""));
      if (r.ocr_used) toast("스캔한 PDF 라서 글자를 인식(OCR)했어요.");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "PDF 를 올리지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  const labels = (except?: string) => fields.filter((f) => f.field_id !== except).map((f) => f.label);
  const uniqueLabel = (base: string) => {
    let l = base || "빈칸";
    let n = 2;
    while (labels().includes(l)) l = `${base || "빈칸"} ${n++}`;
    return l;
  };

  function applyPos(list: PositionSuggestion[]) {
    const created: Field[] = [];
    const used = labels();
    for (const s of list) {
      let l = s.label;
      let n = 2;
      while (used.includes(l)) l = `${s.label} ${n++}`;
      used.push(l);
      created.push({ ...newField(l, s.type), page: s.page, position: s.position });
    }
    setFields((fs) => [...fs, ...created]);
    setPosSugs((x) => x.filter((s) => !list.includes(s)));
  }

  // -------- 포인터: 영역 그리기 / 이동 / 크기 조절 --------
  function rel(e: React.PointerEvent, rect: DOMRect) {
    return { x: clamp((e.clientX - rect.left) / rect.width), y: clamp((e.clientY - rect.top) / rect.height) };
  }

  function onPageDown(page: number) {
    return (e: React.PointerEvent<HTMLDivElement>) => {
      if (!addMode) {
        setSelected(null);
        return;
      }
      const rect = e.currentTarget.getBoundingClientRect();
      const p = rel(e, rect);
      drag.current = { kind: "draw", page, startX: p.x, startY: p.y, rect };
      setDraft({ page, pos: { x: p.x, y: p.y, w: 0.001, h: 0.001 } });
      e.currentTarget.setPointerCapture(e.pointerId);
    };
  }

  function onMove(e: React.PointerEvent) {
    const d = drag.current;
    if (!d || !d.rect) return;
    const p = rel(e, d.rect);
    if (d.kind === "draw") {
      setDraft({ page: d.page, pos: { x: Math.min(p.x, d.startX), y: Math.min(p.y, d.startY), w: Math.max(Math.abs(p.x - d.startX), 0.001), h: Math.max(Math.abs(p.y - d.startY), 0.001) } });
    } else if (d.orig) {
      const dx = p.x - d.startX;
      const dy = p.y - d.startY;
      const o = d.orig;
      const pos = d.kind === "move"
        ? { ...o, x: clamp(o.x + dx, 0, 1 - o.w), y: clamp(o.y + dy, 0, 1 - o.h) }
        : { ...o, w: clamp(o.w + dx, 0.03, 1 - o.x), h: clamp(o.h + dy, 0.015, 1 - o.y) };
      setFields((fs) => fs.map((f) => (f.field_id === d.fieldId ? { ...f, position: pos } : f)));
    }
  }

  function onUp() {
    const d = drag.current;
    drag.current = null;
    if (d?.kind === "draw" && draft && addMode) {
      let pos = draft.pos;
      if (pos.w < 0.03 || pos.h < 0.012) pos = { x: clamp(pos.x, 0, 0.75), y: clamp(pos.y, 0, 0.96), w: 0.25, h: 0.035 }; // 탭만 한 경우 기본 크기
      const f = { ...newField(uniqueLabel(addMode.label), addMode.type), page: draft.page, position: pos };
      setDraft(null);
      setAddMode(null);
      setSheet({ field: f, isNew: true });
    }
  }

  function startFieldDrag(f: Field, kind: "move" | "resize") {
    return (e: React.PointerEvent) => {
      e.stopPropagation();
      if (addMode) return;
      setSelected(f.field_id);
      const pageEl = (e.currentTarget as HTMLElement).closest("[data-page]") as HTMLElement;
      const rect = pageEl.getBoundingClientRect();
      const p = rel(e, rect);
      drag.current = { kind, page: f.page!, startX: p.x, startY: p.y, fieldId: f.field_id, orig: f.position!, rect };
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    };
  }

  async function save() {
    if (!file) return;
    if (!title.trim()) return toast("계약서 제목을 입력해 주세요.", "error");
    if (fields.length === 0) return toast("빈칸을 한 개 이상 추가해 주세요.", "error");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", title.trim().slice(0, 100));
      form.append("contract_type", "general");
      form.append("fields_json", JSON.stringify(fields));
      const r = await api.upload<{ id: string }>("/api/contracts/upload", form);
      nav(`/contracts/${r.id}`, { replace: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "저장하지 못했어요.", "error");
      setBusy(false);
    }
  }

  if (!an) {
    return (
      <Page title="내 PDF 불러오기">
        {busy ? (
          <Loading label="PDF 를 읽고 있어요" />
        ) : (
          <>
            <p className="mt-2 text-[22px] leading-8 font-bold">계약서 PDF 를 올려 주세요</p>
            <p className="mt-2 text-grey-600">빈칸을 찾아 드리고, 직접 빈칸을 추가할 수도 있어요. 스캔한 PDF 도 글자를 인식해요.</p>
            <label className="mt-8 flex h-44 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-grey-300 bg-grey-50 text-grey-600 active:bg-grey-100">
              <span className="text-4xl">📄</span>
              <span className="font-semibold">PDF 파일 선택</span>
              <span className="text-[13px]">최대 10MB · 30쪽</span>
              <input data-testid="pdf-input" type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
            </label>
          </>
        )}
      </Page>
    );
  }

  return (
    <Page title="빈칸 만들기">
      <label className="mb-1.5 block text-[14px] font-medium text-grey-700" htmlFor="pdf-title">계약서 제목</label>
      <input id="pdf-title" data-testid="pdf-title" className="w-full rounded-xl border border-grey-200 px-4 py-3 font-semibold outline-none focus:border-toss-blue" value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} />

      <div className="sticky top-14 z-10 -mx-5 mt-4 flex items-center gap-2 bg-white px-5 py-2">
        <Button size="md" variant={addMode ? "primary" : "secondary"} onClick={() => setAddMode(addMode ? null : { label: "빈칸", type: "TEXT" })} testid="add-field-mode">
          {addMode ? "PDF 에서 영역을 드래그하세요 (취소)" : "+ 빈칸 추가"}
        </Button>
      </div>

      {posSugs.length > 0 && (
        <Card className="mt-2 bg-toss-blue-light p-4">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-toss-blue-dark">빈칸 {posSugs.length}곳을 찾았어요</p>
            <Button size="sm" full={false} onClick={() => applyPos(posSugs)} testid="apply-pos-all">모두 적용</Button>
          </div>
          <p className="mt-1 text-[13px] text-grey-700">점선 상자를 눌러 하나씩 적용할 수도 있어요. 적용한 빈칸은 끌어서 옮기고, 파란 점으로 크기를 바꿀 수 있어요.</p>
        </Card>
      )}
      {textSugs.length > 0 && (
        <Card className="mt-2 p-4">
          <p className="font-semibold">글자 인식으로 찾은 빈칸</p>
          <p className="mb-2 text-[13px] text-grey-600">위치를 알 수 없어요. 누른 뒤 PDF 에서 위치를 드래그해 주세요.</p>
          <div className="flex flex-wrap gap-2">
            {textSugs.map((s) => (
              <button key={s.suggestion_id} className="rounded-xl bg-white px-3 py-1.5 text-[14px] shadow-sm" data-testid={`ocr-sug-${s.label}`}
                onClick={() => { setAddMode({ label: s.label, type: s.type }); setTextSugs((x) => x.filter((y) => y !== s)); }}>
                {s.label} · {FIELD_TYPE_LABEL[s.type]}
              </button>
            ))}
          </div>
        </Card>
      )}

      {err && <p className="mt-4 text-warn">{err}</p>}
      {!doc ? (
        <Loading />
      ) : (
        <div className="mt-3 flex flex-col gap-4" onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
          {an.pages.map((_, i) => {
            const pageNo = i + 1;
            return (
              <div key={pageNo} data-page={pageNo}>
                <p className="mb-1 text-[13px] text-grey-500">{pageNo} / {an.pages.length} 쪽</p>
                <PdfPage doc={doc} pageNo={pageNo} onPointerDown={onPageDown(pageNo)} testid={`pdf-page-${pageNo}`}>
                  {posSugs.filter((s) => s.page === pageNo).map((s, k) => (
                    <button key={k} className="absolute rounded border-2 border-dashed border-toss-blue bg-toss-blue/10 text-[10px] text-toss-blue-dark"
                      style={box(s.position)} onPointerDown={(e) => e.stopPropagation()} onClick={() => applyPos([s])} title={`${s.label} 적용`}>
                      추천: {s.label}
                    </button>
                  ))}
                  {fields.filter((f) => f.page === pageNo && f.position).map((f) => (
                    <div key={f.field_id} data-testid={`box-${f.label}`} className={`absolute rounded border-2 ${selected === f.field_id ? "border-toss-blue bg-toss-blue/20" : "border-[#f59e0b] bg-[#fef3c7]/60"}`}
                      style={box(f.position!)} onPointerDown={startFieldDrag(f, "move")} onDoubleClick={() => setSheet({ field: f, isNew: false })}>
                      <span className="pointer-events-none absolute inset-0 flex items-center overflow-hidden px-0.5 text-[9px] leading-none font-semibold whitespace-nowrap text-grey-800">{f.label}</span>
                      {selected === f.field_id && (
                        <>
                          <div className="absolute top-full left-0 z-10 mt-1 flex gap-1" onPointerDown={(e) => e.stopPropagation()}>
                            <button className="rounded-lg bg-toss-blue px-2 py-1 text-[12px] font-semibold whitespace-nowrap text-white shadow" onClick={() => setSheet({ field: f, isNew: false })} data-testid={`edit-${f.label}`}>설정</button>
                            <button className="rounded-lg bg-white px-2 py-1 text-[12px] font-semibold whitespace-nowrap text-warn shadow" onClick={() => { setFields((fs) => fs.filter((x) => x.field_id !== f.field_id)); setSelected(null); }} data-testid={`remove-${f.label}`}>삭제</button>
                          </div>
                          <span className="absolute -right-2 -bottom-2 h-5 w-5 cursor-se-resize rounded-full border-2 border-white bg-toss-blue shadow" onPointerDown={startFieldDrag(f, "resize")} data-testid={`resize-${f.label}`} />
                        </>
                      )}
                    </div>
                  ))}
                  {draft && draft.page === pageNo && <div className="absolute border-2 border-toss-blue bg-toss-blue/20" style={box(draft.pos)} />}
                </PdfPage>
              </div>
            );
          })}
        </div>
      )}

      <section className="mt-6">
        <h2 className="mb-2 text-[17px] font-bold">빈칸 {fields.length}개</h2>
        <div className="flex flex-wrap gap-2">
          {fields.map((f) => (
            <button key={f.field_id} onClick={() => setSheet({ field: f, isNew: false })} className="rounded-xl bg-grey-100 px-3 py-2 text-[14px]" data-testid={`chip-${f.label}`}>
              <span className="font-semibold">{f.label}</span> <Badge>{FIELD_TYPE_LABEL[f.type]}</Badge> <span className="text-grey-500">{f.page}쪽</span>
            </button>
          ))}
        </div>
      </section>

      <FieldSheet open={!!sheet} field={sheet?.field ?? null} onClose={() => setSheet(null)} usedLabels={labels(sheet?.field.field_id)}
        onSave={(f) => { setFields((fs) => (sheet?.isNew ? [...fs, f] : fs.map((x) => (x.field_id === f.field_id ? f : x)))); setSelected(f.field_id); setSheet(null); }}
        onDelete={sheet && !sheet.isNew ? (f) => { setFields((fs) => fs.filter((x) => x.field_id !== f.field_id)); setSheet(null); } : undefined} />

      <BottomCTA>
        <Button onClick={save} loading={busy} testid="pdf-save">다음</Button>
      </BottomCTA>
    </Page>
  );
}

function box(p: Position) {
  return { left: `${p.x * 100}%`, top: `${p.y * 100}%`, width: `${p.w * 100}%`, height: `${p.h * 100}%` };
}
