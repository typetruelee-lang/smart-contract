import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { getBridge } from "../lib/tossBridge";

const TEST_USERS = [
  { id: "hong", name: "홍길동" },
  { id: "kim", name: "김철수" },
  { id: "lee", name: "이영희" },
];

export default function Login() {
  const { login, user } = useAuth();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [mockLogin, setMockLogin] = useState(true);
  const next = sp.get("next") || "/";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";
  const bridge = getBridge();

  useEffect(() => {
    api.get<{ mock_login: boolean }>("/api/config").then((c) => setMockLogin(c.mock_login)).catch(() => {});
  }, []);
  useEffect(() => {
    if (user) nav(safeNext, { replace: true });
  }, [user, nav, safeNext]);

  async function go(testUser?: string) {
    setBusy(testUser ?? "toss");
    try {
      await login(testUser);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "로그인하지 못했어요.", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Page title="" back={false}>
      <div className="mt-10 flex flex-col gap-3">
        {sp.get("expired") && (
          <div data-testid="session-expired" className="rounded-2xl bg-[#fff4e5] px-4 py-3 text-[15px] text-[#b45309]">
            로그인이 만료되었어요. 다시 로그인해 주세요.
          </div>
        )}
        <h1 className="text-[26px] leading-9 font-bold">
          토스로 로그인하고
          <br />
          계약을 시작하세요
        </h1>
        <p className="text-grey-600">본인 명의의 토스 계정으로 안전하게 로그인해요.</p>
      </div>
      <div className="mt-auto flex flex-col gap-3 pt-10">
        {bridge.isInToss || !mockLogin ? (
          <Button onClick={() => go()} loading={busy === "toss"}>
            토스로 로그인
          </Button>
        ) : (
          <>
            <p className="text-center text-[14px] text-grey-500">개발용 테스트 계정 (토스 로그인 Mock)</p>
            {TEST_USERS.map((u) => (
              <Button key={u.id} testid={`login-${u.id}`} variant={u.id === "hong" ? "primary" : "secondary"} onClick={() => go(u.id)} loading={busy === u.id}>
                {u.name}(으)로 로그인
              </Button>
            ))}
          </>
        )}
      </div>
    </Page>
  );
}
