import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ContractPreview } from "../components/contract";
import { SignaturePad } from "../components/SignaturePad";
import { BottomCTA, Button, Card, Check, ErrorView, Loading, Page, Row, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { displayValue } from "../lib/format";
import type { ContractView } from "../lib/types";

type Step = "identity" | "review" | "sign" | "waiting";

export default function SignFlow() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<ContractView | null>(null);
  const [err, setErr] = useState("");
  const [step, setStep] = useState<Step>("identity");
  const [busy, setBusy] = useState(false);
  const [checks, setChecks] = useState({ content_checked: false, own_will: false, e_signature_consent: false, retention_acknowledged: false });
  const [sig, setSig] = useState<string | null>(null);
  const [legalGrade, setLegalGrade] = useState(false);
  useEffect(() => {
    api.get<{ legal_grade: boolean }>("/api/config").then((c) => setLegalGrade(c.legal_grade)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    try {
      const v = await api.get<ContractView>(`/api/contracts/${id}`);
      if (v.status === "COMPLETED") return nav(`/contracts/${id}/done`, { replace: true });
      const me = v.parties.find((p) => p.is_me)!;
      setC(v);
      if (me.signature_status === "SIGNED" && me.signed_version_no === v.current_version_no) setStep("waiting");
      else if (me.identity_status !== "VERIFIED") setStep("identity");
      else if (!me.reviewed) setStep("review");
      else setStep("sign");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "계약을 불러오지 못했어요.");
    }
  }, [id, nav]);

  useEffect(() => {
    load();
  }, [load]);

  async function verifyIdentity() {
    setBusy(true);
    try {
      const s = await api.post<{ session_id: string }>(`/api/contracts/${id}/identity/start`);
      await api.post(`/api/contracts/${id}/identity/complete`, { session_id: s.session_id });
      toast("본인확인이 끝났어요.");
      setStep("review");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "본인확인에 실패했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function review() {
    setBusy(true);
    try {
      await api.post(`/api/contracts/${id}/review`, { version_no: c!.current_version_no, ...checks });
      setStep("sign");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "확인하지 못했어요.", "error");
      if (e instanceof ApiError && e.code === "VERSION_CHANGED") load();
    } finally {
      setBusy(false);
    }
  }

  async function sign() {
    if (!sig) return toast("서명을 그려 주세요.", "error");
    setBusy(true);
    try {
      const st = await api.post<{ request_id: string; version_no: number }>(`/api/contracts/${id}/sign/start`);
      const r = await api.post<{ completed: boolean }>(`/api/contracts/${id}/sign/complete`, { request_id: st.request_id, version_no: st.version_no, signature_image: sig });
      if (r.completed) nav(`/contracts/${id}/done`, { replace: true });
      else setStep("waiting");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "서명하지 못했어요.", "error");
      if (e instanceof ApiError && ["VERSION_CHANGED", "REVIEW_REQUIRED"].includes(e.code)) load();
    } finally {
      setBusy(false);
    }
  }

  if (err) return <Page title="전자서명"><ErrorView message={err} onRetry={load} /></Page>;
  if (!c) return <Page title="전자서명"><Loading /></Page>;
  const [a, b] = [c.parties.find((p) => p.role === "A"), c.parties.find((p) => p.role === "B")];
  const stepNo = { identity: 1, review: 2, sign: 3, waiting: 3 }[step];

  return (
    <Page title="전자서명" onBack={() => nav(`/contracts/${id}`)}>
      <div className="mb-6 flex gap-1.5" aria-label={`${stepNo}/3 단계`}>
        {[1, 2, 3].map((n) => <div key={n} className={`h-1.5 flex-1 rounded-full ${n <= stepNo ? "bg-toss-blue" : "bg-grey-200"}`} />)}
      </div>

      {step === "identity" && (
        <>
          <h2 className="text-[24px] leading-8 font-bold">먼저 본인확인을 할게요</h2>
          <p className="mt-2 text-grey-600">계약 당사자가 본인이 맞는지 확인해요. 토스 인증으로 간단하게 끝나요.</p>
          <Card className="mt-6 p-4 text-[14px] text-grey-600" testid="identity-mode">
            {legalGrade ? "토스인증 화면에서 본인확인을 진행해요." : "지금은 시험용(모의) 본인확인이에요. 이 환경에서 만든 계약서와 확인서에는 '시험용 · 법적 효력 없음' 이 표시돼요."}
          </Card>
          <BottomCTA><Button onClick={verifyIdentity} loading={busy} testid="identity-btn">토스 인증으로 본인확인</Button></BottomCTA>
        </>
      )}

      {step === "review" && (
        <>
          <h2 className="text-[24px] font-bold">계약 최종 확인</h2>
          <Card className="mt-5 p-4">
            <p className="text-[14px] text-grey-600">당사자</p>
            <p className="mt-1 text-[18px] font-bold">{a?.name ?? "-"} ↔ {b?.name ?? "-"}</p>
          </Card>
          <p className="mt-6 mb-2 text-[14px] text-grey-600">계약 내용 (v{c.current_version_no})</p>
          {c.source === "PDF" ? (
            <Card className="p-4">
              {c.payload?.fields.filter((f) => f.type !== "SIGNATURE").map((f) => <Row key={f.field_id} label={f.label}>{displayValue(f) || "-"}</Row>)}
            </Card>
          ) : (
            <ContractPreview title={c.payload?.title ?? c.title} body={c.payload?.body_text ?? ""} fields={c.payload?.fields ?? []} />
          )}
          <div className="mt-6" data-testid="confirm-checks">
            <Check testid="chk-content" checked={checks.content_checked} onChange={(v) => setChecks({ ...checks, content_checked: v })}>계약 내용을 확인했습니다.</Check>
            <Check testid="chk-will" checked={checks.own_will} onChange={(v) => setChecks({ ...checks, own_will: v })}>본인의 의사로 계약합니다.</Check>
            <Check testid="chk-esign" checked={checks.e_signature_consent} onChange={(v) => setChecks({ ...checks, e_signature_consent: v })}>전자서명으로 계약을 체결합니다.</Check>
            <Check testid="chk-retention" checked={checks.retention_acknowledged} onChange={(v) => setChecks({ ...checks, retention_acknowledged: v })}>
              완성된 계약서 파일은 제가 직접 보관합니다. 서비스는 일정 기간이 지나면 원문을 삭제한다는 것을 알고 있습니다.
            </Check>
          </div>
          <p data-testid="sign-notice" className="mt-3 text-[13px] leading-5 text-grey-500">
            계약 내용은 당사자가 직접 작성한 것이며, 서비스 운영사는 계약의 당사자가 아니고 계약 내용의 적법성이나 이행을 보증하지 않아요. 서명 후에는 되돌릴 수 없으니 내용을 꼼꼼히 확인해 주세요.
          </p>
          <BottomCTA>
            <Button onClick={review} loading={busy} disabled={!Object.values(checks).every(Boolean)} testid="review-btn">다음</Button>
          </BottomCTA>
        </>
      )}

      {step === "sign" && (
        <>
          <h2 className="text-[24px] font-bold">서명해 주세요</h2>
          <p className="mt-2 mb-5 text-grey-600">서명하면 계약 내용(v{c.current_version_no})에 동의한 것으로 기록돼요.</p>
          <SignaturePad onChange={setSig} />
          <BottomCTA>
            <Button onClick={sign} loading={busy} disabled={!sig} testid="sign-btn">전자서명하고 계약 완료</Button>
          </BottomCTA>
        </>
      )}

      {step === "waiting" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center" data-testid="waiting-other">
          <div className="text-5xl">⏳</div>
          <h2 className="text-[22px] font-bold">서명을 마쳤어요</h2>
          <p className="text-grey-600">상대방이 서명하면 계약이 완료돼요.<br />완료되면 계약서 PDF 를 받을 수 있어요.</p>
          <div className="mt-6 w-full"><Button variant="secondary" onClick={() => nav(`/contracts/${id}`)}>계약 화면으로</Button></div>
        </div>
      )}
    </Page>
  );
}
