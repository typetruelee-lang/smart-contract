import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BottomCTA, Button, Card, ErrorView, Loading, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";

export default function Invite() {
  const { token } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [info, setInfo] = useState<{ contract_id: string; title: string; from: string; joined: boolean } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<typeof info>(`/api/invites/${token}`).then(setInfo).catch((e) => setErr(e instanceof ApiError ? e.message : "초대 정보를 불러오지 못했어요."));
  }, [token]);

  async function accept() {
    setBusy(true);
    try {
      const r = await api.post<{ contract_id: string }>(`/api/invites/${token}/accept`);
      nav(`/contracts/${r.contract_id}`, { replace: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "참여하지 못했어요.", "error");
      setBusy(false);
    }
  }

  if (err) return <Page title="계약 참여"><ErrorView message={err} /></Page>;
  if (!info) return <Page title="계약 참여"><Loading /></Page>;
  return (
    <Page title="계약 참여" back={false}>
      <div className="mt-8">
        <p className="text-[15px] font-semibold text-toss-blue">계약 요청이 왔어요</p>
        <h1 className="mt-2 text-[26px] leading-9 font-bold">{info.from}님이<br />계약을 요청했어요</h1>
      </div>
      <Card className="mt-6">
        <p className="text-[14px] text-grey-600">계약서</p>
        <p className="mt-1 text-[18px] font-bold">{info.title}</p>
      </Card>
      <p className="mt-4 text-[14px] leading-6 text-grey-600">참여하면 계약 내용을 확인하고, 내가 입력할 칸을 채운 뒤 본인확인과 전자서명을 할 수 있어요.</p>
      <BottomCTA>
        <Button onClick={accept} loading={busy} testid="accept-invite">계약 내용 확인하기</Button>
      </BottomCTA>
    </Page>
  );
}
