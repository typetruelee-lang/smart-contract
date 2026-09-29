import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge, Card, ErrorView, Loading, Page } from "../components/ui";
import { api } from "../lib/api";
import { formatKst, shortHash } from "../lib/format";

interface Ev {
  event_id: string;
  seq: number;
  event_type: string;
  timestamp: string;
  actor_id: string | null;
  document_version: number | null;
  document_hash: string | null;
  metadata: Record<string, unknown>;
}

const LABEL: Record<string, string> = {
  CONTRACT_CREATED: "계약서 작성", CONTRACT_VIEWED: "계약서 열람", CONTRACT_UPDATED: "내용 수정", VERSION_CREATED: "새 버전 생성", INVITED: "상대방 초대",
  INVITE_ACCEPTED: "상대방 참여", IDENTITY_VERIFIED: "본인확인 완료", CONTRACT_REVIEWED: "최종 확인", SIGNATURE_STARTED: "서명 시작", SIGNATURE_COMPLETED: "서명 완료",
  SIGNATURE_INVALIDATED: "서명 무효화(내용 변경)", CONTRACT_COMPLETED: "계약 완료", CONTRACT_CANCELED: "계약 취소", PDF_GENERATED: "계약서 PDF 생성", HASH_CREATED: "디지털 지문 생성",
  CERTIFICATE_GENERATED: "확인서 발급", PAYMENT_REQUESTED: "결제 요청", PAYMENT_SUCCEEDED: "결제 완료", PAYMENT_FAILED: "결제 실패", BLOCKCHAIN_SUBMITTED: "블록체인 전송",
  BLOCKCHAIN_RETRY: "블록체인 재시도", BLOCKCHAIN_CONFIRMED: "블록체인 기록 확인", BLOCKCHAIN_FAILED: "블록체인 기록 실패", DOCUMENT_PURGED: "원문 삭제(보존기간 만료)",
};

export default function Evidence() {
  const { id } = useParams();
  const [data, setData] = useState<{ events: Ev[]; chain_valid: boolean } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get<typeof data>(`/api/contracts/${id}/events`).then(setData).catch((e) => setErr(e.message));
  }, [id]);
  if (err) return <Page title="진행 기록"><ErrorView message={err} /></Page>;
  if (!data) return <Page title="진행 기록"><Loading /></Page>;
  return (
    <Page title="진행 기록 (감사 로그)">
      <Card className="mb-4 p-4">
        <div className="flex items-center justify-between">
          <span className="font-semibold">기록 무결성</span>
          {data.chain_valid ? <Badge tone="green">위·변조 없음</Badge> : <Badge tone="red">변조 의심</Badge>}
        </div>
        <p className="mt-1 text-[13px] text-grey-600">각 기록은 이전 기록의 지문을 포함해 사슬처럼 연결되어 있어요.</p>
      </Card>
      <ol className="relative ml-2 border-l-2 border-grey-100" data-testid="event-list">
        {data.events.map((e) => (
          <li key={e.event_id} className="mb-4 ml-4">
            <span className="absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full bg-toss-blue" />
            <p className="font-semibold">{LABEL[e.event_type] ?? e.event_type}</p>
            <p className="text-[13px] text-grey-500">{formatKst(e.timestamp)}{e.document_version ? ` · v${e.document_version}` : ""}{e.metadata.role ? ` · 당사자 ${e.metadata.role}` : ""}</p>
            {e.document_hash && <p className="font-mono text-[12px] text-grey-400">{shortHash(e.document_hash)}</p>}
            <p className="text-[11px] text-grey-400">{e.event_type}</p>
          </li>
        ))}
      </ol>
    </Page>
  );
}
