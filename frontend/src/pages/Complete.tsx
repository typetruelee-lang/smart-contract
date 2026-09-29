import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, ErrorView, Loading, Page, Row, Sheet, useToast } from "../components/ui";
import { ApiError, api, downloadFile } from "../lib/api";
import { ANCHOR_LABEL, formatKst, shortHash, won } from "../lib/format";
import { getBridge } from "../lib/tossBridge";
import type { ContractView } from "../lib/types";

export default function Complete() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<ContractView | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [pay, setPay] = useState<{ payment_id: string; amount: number; provider: string; order_id: string; client_params: { sku?: string } } | null>(null);

  const load = useCallback(async () => {
    try {
      const v = await api.get<ContractView>(`/api/contracts/${id}`);
      if (v.status !== "COMPLETED") return nav(`/contracts/${id}`, { replace: true });
      setC(v);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "계약을 불러오지 못했어요.");
    }
  }, [id, nav]);

  useEffect(() => {
    load();
  }, [load]);

  // 기록 진행 중이면 주기적으로 상태 갱신
  useEffect(() => {
    if (!c || !["PENDING", "RETRY", "SUBMITTED"].includes(c.anchor.status)) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [c, load]);

  async function dl(kind: "contract" | "certificate") {
    setBusy(kind);
    try {
      await downloadFile(`/api/contracts/${id}/pdf/${kind}`, kind === "contract" ? `${c!.contract_no}.pdf` : `${c!.contract_no}-전자계약확인서.pdf`);
      toast(kind === "contract" ? "계약서 PDF 를 저장했어요. 안전하게 보관해 주세요." : "전자계약 확인서를 저장했어요.");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "파일을 받지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  async function checkout() {
    setBusy("checkout");
    try {
      const r = await api.post<NonNullable<typeof pay>>(`/api/contracts/${id}/anchor/checkout`);
      if (r.provider === "mock") {
        setPay(r); // 개발용 모의 결제 시트
      } else {
        // 운영: 앱인토스 인앱결제 창 → 결과를 서버에서 검증
        const res = await getBridge().purchase(r.client_params.sku ?? "", r.order_id);
        setPay(r);
        await confirm(res.result, r, res.payload);
      }
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "결제를 시작하지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  async function confirm(result: "success" | "fail" | "cancel", p = pay, providerPayload: Record<string, unknown> = {}) {
    if (!p) return;
    setBusy(result);
    try {
      const r = await api.post<{ payment_status: string; anchor_status: string; reason?: string }>(`/api/contracts/${id}/anchor/confirm`, { payment_id: p.payment_id, result, provider_payload: providerPayload });
      setPay(null);
      if (r.payment_status !== "PAID") toast(r.reason ?? "결제가 완료되지 않았어요. 기록하지 않았어요.", "error");
      else if (r.anchor_status === "CONFIRMED") toast("디지털 지문을 블록체인에 기록했어요.");
      else toast("결제는 완료됐어요. 기록이 조금 늦어지고 있어요. 자동으로 다시 시도할게요.");
      await load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "결제를 확인하지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  async function retry() {
    setBusy("retry");
    try {
      await api.post(`/api/contracts/${id}/anchor/retry`);
      await load();
    } finally {
      setBusy("");
    }
  }

  async function extend() {
    setBusy("extend");
    try {
      await api.post(`/api/contracts/${id}/retention/extend`);
      toast("보관 기간을 연장했어요.");
      await load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "연장하지 못했어요.", "error");
    } finally {
      setBusy("");
    }
  }

  if (err) return <Page title="계약 완료"><ErrorView message={err} onRetry={load} /></Page>;
  if (!c) return <Page title="계약 완료"><Loading /></Page>;
  const [a, b] = [c.parties.find((p) => p.role === "A"), c.parties.find((p) => p.role === "B")];
  const all = (k: "identity" | "sign") => c.parties.every((p) => (k === "identity" ? p.identity_status === "VERIFIED" : p.signature_status === "SIGNED"));
  const an = c.anchor;

  return (
    <Page title="" onBack={() => nav("/")}>
      <div className="mt-4 text-center" data-testid="complete-hero">
        <div className="text-[56px]">🎉</div>
        <h1 className="mt-2 text-[24px] font-bold">계약이 완료되었어요</h1>
        <p className="mt-2 text-[18px] font-semibold text-grey-700">{a?.name} ↔ {b?.name}</p>
      </div>

      <Card className="mt-6 p-4">
        <p className="py-1 text-[16px]">{all("identity") ? "✅" : "⬜"} 본인확인</p>
        <p className="py-1 text-[16px]">{all("sign") ? "✅" : "⬜"} 전자서명</p>
        <p className="py-1 text-[16px]">✅ 계약 완료 <span className="text-[13px] text-grey-500">· {formatKst(c.completed_at)}</span></p>
      </Card>

      <div className="mt-5 flex flex-col gap-2">
        <Button onClick={() => dl("contract")} loading={busy === "contract"} disabled={c.purged} testid="dl-contract">계약서 PDF 저장</Button>
        <Button variant="secondary" onClick={() => dl("certificate")} loading={busy === "certificate"} testid="dl-certificate">전자계약 확인서</Button>
      </div>
      <p className="mt-3 text-[13px] leading-5 text-grey-500">
        {c.purged ? "보관 기간이 지나 원본이 삭제되었어요. 내려받은 PDF 를 사용해 주세요." : `🔒 ${c.retention_note ?? ""} (삭제 예정: ${formatKst(c.purge_at)})`}
      </p>
      {c.allow_extended_retention && !c.keep_encrypted_original && !c.purged && c.my_role === "A" && (
        <Button size="sm" variant="ghost" full={false} onClick={extend} loading={busy === "extend"}>암호화 보관 기간 연장 (근로계약)</Button>
      )}

      <Card className="mt-4 p-4">
        <Row label="검증번호">{c.verification_id}</Row>
        <Row label="디지털 지문" mono>{shortHash(c.document_hash)}</Row>
        <button className="mt-1 text-[14px] text-toss-blue" onClick={() => nav(`/verify/${c.verification_id}`)}>검증 페이지 열기 →</button>
      </Card>

      {c.blockchain_enabled && (
        <section className="mt-8 border-t border-grey-100 pt-6" data-testid="anchor-section">
          <h2 className="text-[19px] font-bold">🔐 계약을 블록체인에 기록</h2>
          <p className="mt-2 text-[15px] leading-6 text-grey-600">계약서 원본은 저장하지 않고 디지털 지문만 기록해요. 나중에 누구나 계약서가 바뀌지 않았다는 걸 확인할 수 있어요.</p>
          {an.status === "NOT_REQUESTED" ? (
            <div className="mt-4">
              {c.payment.status === "FAILED" || c.payment.status === "CANCELED" ? <p className="mb-2 text-[14px] text-warn" data-testid="payment-failed">결제가 완료되지 않아 기록하지 않았어요. 다시 시도할 수 있어요.</p> : null}
              <Button onClick={checkout} loading={busy === "checkout"} testid="anchor-buy">{won(c.blockchain_price)}에 기록하기</Button>
            </div>
          ) : (
            <Card className="mt-4 p-4" testid="anchor-status">
              <div className="flex items-center justify-between">
                <span className="font-semibold">기록 상태</span>
                <Badge tone={an.status === "CONFIRMED" ? "green" : an.status === "FAILED" ? "red" : "orange"}>{ANCHOR_LABEL[an.status]}</Badge>
              </div>
              <Row label="결제">{c.payment.status === "PAID" ? "결제 완료" : c.payment.status}</Row>
              {an.tx_id && <Row label="Blockchain TX" mono>{an.tx_id.slice(0, 18)}…</Row>}
              {an.network && <Row label="네트워크">{an.network}</Row>}
              {an.confirmed_at && <Row label="기록 시각">{formatKst(an.confirmed_at)}</Row>}
              {["PENDING", "RETRY", "SUBMITTED"].includes(an.status) && (
                <>
                  <p className="mt-2 text-[14px] text-grey-600">결제는 완료됐어요. 기록이 늦어지고 있어 자동으로 다시 시도하고 있어요. (시도 {an.attempts}회)</p>
                  <Button size="sm" variant="secondary" full={false} onClick={retry} loading={busy === "retry"} testid="anchor-retry">지금 다시 시도</Button>
                </>
              )}
              {an.status === "FAILED" && <p className="mt-2 text-[14px] text-warn">기록에 실패했어요. 결제는 보호되며 고객센터에서 도와드릴게요.</p>}
            </Card>
          )}
        </section>
      )}

      <div className="mt-8 flex gap-2">
        <Button size="sm" variant="ghost" full={false} onClick={() => nav(`/contracts/${id}/evidence`)}>진행 기록 보기</Button>
        <Button size="sm" variant="ghost" full={false} onClick={() => nav("/")}>홈으로</Button>
      </div>

      <Sheet open={!!pay && pay.provider === "mock"} onClose={() => !busy && setPay(null)} title="결제하기">
        <Card className="p-4">
          <Row label="상품">블록체인 기록 (디지털 지문)</Row>
          <Row label="금액">{won(pay?.amount ?? 0)}</Row>
        </Card>
        <p className="mt-3 text-[13px] text-grey-500">개발 환경의 모의 결제예요. 실제 서비스에서는 토스 결제 화면이 열려요.</p>
        <div className="flex flex-col gap-2 py-4">
          <Button onClick={() => confirm("success")} loading={busy === "success"} testid="pay-success">결제하기</Button>
          <div className="grid grid-cols-2 gap-2">
            <Button size="md" variant="danger" onClick={() => confirm("fail")} loading={busy === "fail"} testid="pay-fail">결제 실패 (테스트)</Button>
            <Button size="md" variant="ghost" onClick={() => confirm("cancel")} loading={busy === "cancel"} testid="pay-cancel">취소</Button>
          </div>
        </div>
      </Sheet>
    </Page>
  );
}
