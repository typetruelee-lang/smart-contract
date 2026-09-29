import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, Loading, Page, Row, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { ANCHOR_LABEL, formatKst, shortHash } from "../lib/format";
import { sha256File } from "../lib/hash";

interface PublicInfo {
  verification_id: string;
  contract_status: string;
  completed_at: string | null;
  document_hash: string;
  document_hash_short: string;
  anchor: { status: string; tx_id?: string; network?: string; confirmed_at?: string; mode?: string; merkle_root?: string | null };
}
interface CheckResult extends Partial<PublicInfo> {
  match: boolean;
  uploaded_hash: string;
  message: string;
  reason?: string;
  onchain?: { recorded: boolean | null; recorded_at?: string; proof_valid?: boolean } | null;
}

export default function Verify() {
  const { vid } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [input, setInput] = useState(vid ?? "");
  const [info, setInfo] = useState<PublicInfo | null>(null);
  const [notFound, setNotFound] = useState("");
  const [loading, setLoading] = useState(Boolean(vid));
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState("");

  useEffect(() => {
    setResult(null);
    if (!vid) {
      setInfo(null);
      return;
    }
    setLoading(true);
    api.get<PublicInfo>(`/api/verify/${encodeURIComponent(vid)}`)
      .then((r) => { setInfo(r); setNotFound(""); })
      .catch((e) => { setInfo(null); setNotFound(e instanceof ApiError ? e.message : "검증번호를 찾을 수 없어요."); })
      .finally(() => setLoading(false));
  }, [vid]);

  async function onFile(f: File | undefined) {
    if (!f) return;
    setBusy(true);
    setFileName(f.name);
    try {
      // 파일은 서버로 보내지 않고, 브라우저에서 디지털 지문(SHA-256)만 계산해서 보낸다
      const hash = await sha256File(f);
      const r = await api.post<CheckResult>("/api/verify/check", { document_hash: hash, verification_id: vid ?? null });
      setResult(r);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "검증하지 못했어요.", "error");
    } finally {
      setBusy(false);
    }
  }

  const lookup = () => input.trim() && nav(`/verify/${encodeURIComponent(input.trim().toUpperCase())}`);

  return (
    <Page title="전자계약 검증" onBack={() => nav("/")}>
      {!vid && (
        <>
          <h2 className="mt-2 text-[22px] leading-8 font-bold">계약서가 바뀌지 않았는지<br />확인해 보세요</h2>
          <p className="mt-2 text-grey-600">검증번호(확인서의 QR)를 입력하거나, 계약서 PDF 를 바로 올려도 돼요.</p>
          <div className="mt-6 flex gap-2">
            <input data-testid="verify-id-input" className="min-w-0 flex-1 rounded-xl border border-grey-200 px-4 py-3 font-mono uppercase outline-none focus:border-toss-blue" placeholder="V-XXXX-XXXX-XXXX"
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && lookup()} maxLength={24} />
            <Button full={false} size="md" onClick={lookup} testid="verify-lookup">조회</Button>
          </div>
        </>
      )}

      {loading && <Loading />}
      {notFound && <Card className="mt-6 bg-[#fff0f1]"><p className="font-semibold text-warn">{notFound}</p></Card>}

      {info && (
        <Card className="mt-2 p-4" testid="verify-info">
          <p className="mb-1 text-[14px] text-grey-600">검증번호</p>
          <p className="mb-3 font-mono text-[18px] font-bold">{info.verification_id}</p>
          <Row label="계약 상태"><Badge tone="green">완료</Badge></Row>
          <Row label="완료 일시">{formatKst(info.completed_at)}</Row>
          <Row label="디지털 지문" mono>{info.document_hash_short}</Row>
          <Row label="블록체인">{ANCHOR_LABEL[info.anchor.status] ?? info.anchor.status}</Row>
          {info.anchor.confirmed_at && <Row label="기록 일시">{formatKst(info.anchor.confirmed_at)}</Row>}
          {info.anchor.tx_id && <Row label="TX" mono>{info.anchor.tx_id.slice(0, 20)}…</Row>}
        </Card>
      )}

      {(info || !vid) && (
        <label className="mt-6 flex h-32 cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-grey-300 bg-grey-50 text-grey-600 active:bg-grey-100">
          <span className="text-3xl">📄</span>
          <span className="font-semibold">{busy ? "확인 중…" : fileName ? "다른 PDF 로 다시 확인" : "계약서 PDF 올려서 확인"}</span>
          <span className="text-[12px]">파일은 서버로 전송되지 않아요</span>
          <input data-testid="verify-file" type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      )}

      {result && (
        <Card className={`mt-4 p-5 ${result.match ? "bg-[#e5f8ee]" : "bg-[#fff0f1]"}`} testid={result.match ? "verify-success" : "verify-failed"}>
          <p className={`text-[20px] font-bold ${result.match ? "text-ok" : "text-warn"}`}>{result.match ? "✓ 검증 성공" : "⚠ 검증 실패"}</p>
          <p className="mt-2 text-[15px] leading-6 text-grey-800">
            {result.match ? <>문서의 디지털 지문이<br />기록된 값과 일치합니다.</> : result.reason === "NOT_FOUND" ? <>이 문서의 디지털 지문과<br />일치하는 계약 기록이 없어요.</> : <>현재 문서의 디지털 지문이<br />기록된 값과 다릅니다.</>}
          </p>
          <div className="mt-3 border-t border-black/5 pt-2">
            <Row label="올린 파일" mono>{shortHash(result.uploaded_hash)}</Row>
            {result.document_hash && <Row label="기록된 값" mono>{shortHash(result.document_hash)}</Row>}
            {result.match && result.verification_id && !vid && <Row label="검증번호">{result.verification_id}</Row>}
            {result.onchain && <Row label="블록체인 확인">{result.onchain.recorded ? "✓ 기록 확인됨" : result.onchain.recorded === false ? "기록 없음" : "조회 실패"}</Row>}
          </div>
        </Card>
      )}
      <p className="mt-6 text-[13px] leading-5 text-grey-500">이 페이지에는 이름·연락처·계약 내용 같은 개인정보가 표시되지 않아요.</p>
    </Page>
  );
}
