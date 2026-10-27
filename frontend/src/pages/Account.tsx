import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Page, Row, Sheet, useToast } from "../components/ui";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Account() {
  const nav = useNavigate();
  const toast = useToast();
  const { user, logout, withdraw } = useAuth();
  const [confirm, setConfirm] = useState(false);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);

  async function doWithdraw() {
    setBusy(true);
    try {
      const r = await withdraw();
      toast(r.canceled_contracts > 0 ? `탈퇴했어요. 진행 중이던 계약 ${r.canceled_contracts}건을 취소했어요.` : "탈퇴했어요. 그동안 이용해 주셔서 고마워요.");
      nav("/", { replace: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "탈퇴하지 못했어요. 잠시 후 다시 시도해 주세요.", "error");
      setBusy(false);
    }
  }

  return (
    <Page title="내 정보">
      <Card className="mt-2 p-5">
        <Row label="이름">{user?.name}</Row>
        <Row label="로그인">토스</Row>
      </Card>
      <div className="mt-4 flex flex-col gap-2">
        <Button variant="ghost" onClick={() => nav("/contracts")}>내 계약 보기</Button>
        <Button variant="ghost" onClick={() => nav("/terms")}>이용약관</Button>
        <Button variant="ghost" onClick={() => nav("/privacy")}>개인정보처리방침</Button>
        <Button variant="ghost" testid="logout" onClick={async () => { await logout(); nav("/", { replace: true }); }}>로그아웃</Button>
      </div>
      <button data-testid="withdraw-open" onClick={() => setConfirm(true)} className="mt-10 text-[14px] text-grey-500 underline">회원 탈퇴</button>

      <Sheet open={confirm} onClose={() => !busy && setConfirm(false)} title="정말 탈퇴할까요?">
        <ul className="list-disc space-y-1.5 pl-5 text-[14px] leading-6 text-grey-700">
          <li>작성 중이거나 서명을 기다리는 계약은 <b>모두 취소</b>되고 원문이 바로 삭제돼요. 상대방에게는 계약 취소로 보여요.</li>
          <li>이미 완료된 계약은 상대방도 보관·검증할 수 있어야 해서 남아 있어요. 원문은 보존 기간이 지나면 삭제되고, 디지털 지문과 진행 기록(가려진 이름)만 남아요.</li>
          <li>완료된 계약서 PDF가 필요하면 탈퇴 전에 꼭 내려받아 두세요. 탈퇴 후에는 다시 받을 수 없어요.</li>
        </ul>
        <label className="mt-4 flex items-start gap-2 text-[14px]">
          <input type="checkbox" data-testid="withdraw-agree" className="mt-1 h-5 w-5" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <span>위 내용을 확인했어요.</span>
        </label>
        <div className="flex flex-col gap-2 py-4">
          <Button variant="danger" disabled={!agree} loading={busy} onClick={doWithdraw} testid="withdraw-confirm">탈퇴하기</Button>
          <Button variant="ghost" onClick={() => setConfirm(false)} disabled={busy}>취소</Button>
        </div>
      </Sheet>
    </Page>
  );
}
