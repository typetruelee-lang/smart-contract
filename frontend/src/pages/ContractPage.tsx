import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ClausePanel } from "../components/clauses";
import { ContractPreview, EditPreviewToggle, FieldInput } from "../components/contract";
import { PdfPage, usePdf } from "../components/PdfCanvas";
import { Badge, BottomCTA, Button, Card, ErrorView, Loading, Page, Row, Sheet, useToast } from "../components/ui";
import { ApiError, api, downloadFile } from "../lib/api";
import { STATUS_LABEL, displayValue, formatKst } from "../lib/format";
import { getBridge } from "../lib/tossBridge";
import type { ContractView, Field } from "../lib/types";

export default function ContractPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<ContractView | null>(null);
  const [err, setErr] = useState("");
  const [values, setValues] = useState<Record<string, Field["value"]>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [busy, setBusy] = useState("");
  const [invite, setInvite] = useState<{ url: string; expires_at: string } | null>(null);
  const [diff, setDiff] = useState<{ from: number; to: number; changes: { label: string; before: unknown; after: unknown }[] } | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const load = useCallback(async () => {
    try {
      const v = await api.get<ContractView>(`/api/contracts/${id}`);
      setC(v);
      setValues({});
      setErrors({});
      setErr("");
      const me = v.parties.find((p) => p.is_me);
      if (v.current_version_no > 1 && me && !me.reviewed && v.status !== "COMPLETED") {
        api.get<typeof diff>(`/api/contracts/${id}/versions/${v.current_version_no - 1}/diff/${v.current_version_no}`).then(setDiff).catch(() => {});
      } else setDiff(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "계약을 불러오지 못했어요.");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const fields = useMemo(() => (c?.payload?.fields ?? []).map((f) => (f.field_id in values ? { ...f, value: values[f.field_id] } : f)), [c, values]);

  if (err) return <Page title="계약"><ErrorView message={err} onRetry={load} /></Page>;
  if (!c) return <Page title="계약"><Loading /></Page>;
  if (c.status === "COMPLETED") return <Navigate to={`/contracts/${c.id}/done`} replace />;

  const me = c.parties.find((p) => p.is_me)!;
  const editable = !["COMPLETED", "CANCELED", "EXPIRED"].includes(c.status) && !c.purged;
  const mine = (f: Field) => f.assignee === me.role || f.assignee === "ANY";
  const myFields = fields.filter((f) => mine(f) && f.type !== "SIGNATURE");
  const dirty = Object.keys(values).length > 0;
  const bothJoined = c.parties.length >= 2 && c.parties.every((p) => p.joined);
  const missingMine = myFields.filter((f) => f.required && (f.value === null || f.value === "" || (f.type === "CHECKBOX" && f.value !== true)));
  const missingAll = fields.filter((f) => f.type !== "SIGNATURE" && f.required && (f.value === null || f.value === "" || (f.type === "CHECKBOX" && f.value !== true)));

  async function saveValues(): Promise<boolean> {
    if (!dirty) return true;
    setBusy("save");
    try {
      await api.put(`/api/contracts/${id}/values`, { values });
      await load();
      toast("저장했어요.");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.extra.field_id) setErrors({ [String(e.extra.field_id)]: e.message });
      toast(e instanceof ApiError ? e.message : "저장하지 못했어요.", "error");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function doInvite() {
    if (!(await saveValues())) return;
    setBusy("invite");
    try {
      const r = await api.post<{ invite_url: string; expires_at: string }>(`/api/contracts/${id}/invite`);
      setInvite({ url: r.invite_url, expires_at: r.expires_at });
      await load();
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.extra.field_ids)) setErrors(Object.fromEntries((e.extra.field_ids as string[]).map((f) => [f, "꼭 입력해 주세요."])));
      toast(e instanceof ApiError ? e.message : "초대하지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  async function share() {
    if (!invite) return;
    const r = await getBridge().share(`[계약하자] ${c!.title} 계약에 참여해 주세요`, invite.url);
    toast(r === "copied" ? "초대 링크를 복사했어요. 상대방에게 보내 주세요." : "공유했어요.");
  }

  async function goSign() {
    if (!(await saveValues())) return;
    nav(`/contracts/${id}/sign`);
  }

  async function cancel() {
    setBusy("cancel");
    try {
      await api.post(`/api/contracts/${id}/cancel`);
      toast("계약을 취소했어요.");
      nav("/", { replace: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "취소하지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  let cta: React.ReactNode = null;
  if (editable) {
    if (["DRAFT", "READY"].includes(c.status) && me.role === "A") {
      cta = <Button onClick={doInvite} loading={busy === "invite"} testid="invite-btn" disabled={missingMine.length > 0 && !dirty}>{missingMine.length > 0 ? `내 칸 ${missingMine.length}개를 채워 주세요` : "상대방에게 계약 요청하기"}</Button>;
    } else if (!bothJoined && me.role === "A") {
      cta = <Button onClick={doInvite} variant="secondary" loading={busy === "invite"} testid="reinvite-btn">초대 링크 다시 보내기</Button>;
    } else if (bothJoined && me.signature_status !== "SIGNED") {
      cta = (
        <Button onClick={goSign} testid="go-sign" disabled={missingAll.length > 0 && !dirty}>
          {missingMine.length > 0 ? `내 칸 ${missingMine.length}개를 채워 주세요` : missingAll.length > 0 ? "상대방이 입력을 마치면 서명할 수 있어요" : "내용 확인하고 서명하기"}
        </Button>
      );
    } else if (me.signature_status === "SIGNED") {
      cta = <Button variant="ghost" disabled>상대방의 서명을 기다리고 있어요</Button>;
    }
  }

  return (
    <Page title={c.title} onBack={() => nav("/")}>
      <div className="flex items-center gap-2">
        <Badge tone={c.status === "SIGNING" ? "blue" : "grey"}>{STATUS_LABEL[c.status]}</Badge>
        <span className="text-[13px] text-grey-500">v{c.current_version_no} · {c.contract_no}</span>
      </div>

      {diff && diff.changes.length > 0 && (
        <Card className="mt-4 border border-[#fcd34d] bg-[#fffbeb] p-4" testid="version-changed">
          <p className="font-semibold text-[#92400e]">계약 내용이 바뀌었어요 (v{diff.from} → v{diff.to})</p>
          <ul className="mt-2 flex flex-col gap-1 text-[14px] text-grey-800">
            {diff.changes.slice(0, 6).map((ch, i) => (
              <li key={i}>
                <b>{ch.label}</b>: <s className="text-grey-500">{String(ch.before ?? "비어 있음").slice(0, 40)}</s> → {String(ch.after ?? "비어 있음").slice(0, 40)}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[13px] text-grey-600">바뀐 내용을 확인한 뒤 다시 서명해 주세요.</p>
        </Card>
      )}

      <Card className="mt-4 p-4">
        {c.parties.map((p) => (
          <div key={p.role} className="flex items-center justify-between py-1.5">
            <span className="text-grey-700">{p.role_label}{p.is_me && " · 나"}</span>
            <span className="text-[14px] font-medium">
              {p.joined ? p.name : p.invite_pending ? "초대 수락 대기" : "초대 전"}{" "}
              {p.signature_status === "SIGNED" ? <Badge tone="green">서명 완료</Badge> : p.signature_status === "INVALIDATED" ? <Badge tone="orange">다시 서명 필요</Badge> : null}
            </span>
          </div>
        ))}
        {c.parties.length < 2 && <div className="flex justify-between py-1.5"><span className="text-grey-700">당사자 B (상대방)</span><span className="text-[14px] text-grey-500">초대 전</span></div>}
      </Card>

      <div className="mt-5"><EditPreviewToggle mode={mode} onChange={setMode} /></div>

      {mode === "preview" ? (
        <div className="mt-4">
          {c.source === "PDF" ? <PdfPreview id={c.id} fields={fields} /> : <ContractPreview title={c.payload?.title ?? c.title} body={c.payload?.body_text ?? ""} fields={fields} highlight={me.role} />}
          <Button variant="ghost" size="md" onClick={() => downloadFile(`/api/contracts/${id}/pdf/preview`, `${c.contract_no}-preview.pdf`).catch(() => toast("미리보기 PDF 를 만들지 못했어요.", "error"))}>
            미리보기 PDF 받기
          </Button>
        </div>
      ) : (
        <div className="mt-4 flex flex-col gap-3" data-testid="my-fields">
          {myFields.length === 0 ? (
            <p className="text-grey-600">내가 입력할 칸이 없어요.</p>
          ) : (
            <>
              <p className="text-[15px] font-semibold">내가 입력할 칸 {myFields.length}개</p>
              {myFields.map((f) => (
                <FieldInput key={f.field_id} f={f} value={f.value} disabled={!editable} error={errors[f.field_id]}
                  onChange={(v) => { setValues((x) => ({ ...x, [f.field_id]: v })); setErrors((e) => ({ ...e, [f.field_id]: "" })); }} />
              ))}
              {dirty && <Button variant="secondary" size="md" onClick={saveValues} loading={busy === "save"} testid="save-values">입력 내용 저장</Button>}
            </>
          )}
          {fields.filter((f) => !mine(f) && f.type !== "SIGNATURE").length > 0 && (
            <Card className="mt-2 p-4">
              <p className="mb-1 text-[14px] font-semibold text-grey-700">상대방이 입력하는 칸</p>
              {fields.filter((f) => !mine(f) && f.type !== "SIGNATURE").map((f) => (
                <Row key={f.field_id} label={f.label}>{displayValue(f) || <span className="text-grey-400">입력 전</span>}</Row>
              ))}
            </Card>
          )}
          {c.source !== "PDF" && (
            <div className="mt-2">
              <ClausePanel c={c} canEdit={editable && me.role === "A"} beforeChange={saveValues} onChanged={load} />
            </div>
          )}
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        {editable && me.role === "A" && c.source !== "PDF" && <Button size="sm" variant="ghost" full={false} onClick={() => nav(`/contracts/${id}/edit`)} testid="edit-content">계약서 내용 수정</Button>}
        <Button size="sm" variant="ghost" full={false} onClick={() => nav(`/contracts/${id}/evidence`)}>진행 기록 보기</Button>
        {editable && me.role === "A" && <Button size="sm" variant="danger" full={false} onClick={() => setConfirmCancel(true)}>계약 취소</Button>}
      </div>
      {c.retention_note && <p className="mt-4 text-[13px] leading-5 text-grey-500">🔒 {c.retention_note}</p>}

      <Sheet open={!!invite} onClose={() => setInvite(null)} title="상대방에게 초대 링크를 보내 주세요">
        <p className="text-grey-600">링크를 받은 사람이 토스로 로그인하면 계약에 참여할 수 있어요.</p>
        <div data-testid="invite-url" className="mt-4 rounded-xl bg-grey-100 p-3 font-mono text-[13px] break-all">{invite?.url}</div>
        <p className="mt-2 text-[13px] text-grey-500">만료: {formatKst(invite?.expires_at)} · 1회만 사용할 수 있어요</p>
        <div className="flex flex-col gap-2 py-4">
          <Button onClick={share} testid="share-invite">링크 공유하기</Button>
          <Button variant="ghost" onClick={() => setInvite(null)}>닫기</Button>
        </div>
      </Sheet>
      <Sheet open={confirmCancel} onClose={() => setConfirmCancel(false)} title="계약을 취소할까요?">
        <p className="text-grey-600">취소하면 계약서 원문이 삭제되고 되돌릴 수 없어요.</p>
        <div className="flex gap-2 py-4">
          <Button variant="ghost" onClick={() => setConfirmCancel(false)}>아니요</Button>
          <Button variant="danger" onClick={cancel} loading={busy === "cancel"}>취소하기</Button>
        </div>
      </Sheet>

      {cta && <BottomCTA>{cta}</BottomCTA>}
    </Page>
  );
}

function PdfPreview({ id, fields }: { id: string; fields: Field[] }) {
  const [buf, setBuf] = useState<ArrayBuffer | null>(null);
  const { doc, err } = usePdf(buf);
  const [pages, setPages] = useState(0);
  useEffect(() => {
    api.blob(`/api/contracts/${id}/source.pdf`).then((b) => b.arrayBuffer()).then(setBuf).catch(() => {});
  }, [id]);
  useEffect(() => {
    if (doc) setPages(doc.numPages);
  }, [doc]);
  if (err) return <p className="text-warn">{err}</p>;
  if (!doc) return <Loading />;
  return (
    <div className="mb-3 flex flex-col gap-3">
      {Array.from({ length: pages }, (_, i) => (
        <PdfPage key={i} doc={doc} pageNo={i + 1}>
          {fields.filter((f) => f.page === i + 1 && f.position).map((f) => (
            <div key={f.field_id} className="absolute flex items-center overflow-hidden rounded-sm bg-toss-blue/10 px-0.5 text-[9px] font-semibold text-toss-blue-dark"
              style={{ left: `${f.position!.x * 100}%`, top: `${f.position!.y * 100}%`, width: `${f.position!.w * 100}%`, height: `${f.position!.h * 100}%` }}>
              {f.type === "SIGNATURE" ? (f.value ? "✍️" : f.label) : displayValue(f) || f.label}
            </div>
          ))}
        </PdfPage>
      ))}
    </div>
  );
}
