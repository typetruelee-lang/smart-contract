import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, Page, Section } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { STATUS_LABEL } from "../lib/format";
import { LegalFooter } from "../components/legal";
import type { ContractSummary } from "../lib/types";

const QUICK = [
  { id: "loan", name: "차용증", emoji: "💰" },
  { id: "service", name: "용역계약", emoji: "🛠️" },
  { id: "employment", name: "근로계약", emoji: "👷" },
  { id: "goods", name: "거래계약", emoji: "📦" },
];

export default function Home() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [mine, setMine] = useState<ContractSummary[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api.get<{ contracts: ContractSummary[] }>("/api/contracts").then((r) => setMine(r.contracts)).catch(() => setMine([]));
  }, [user]);

  const start = (path: string) => nav(user ? path : `/login?next=${encodeURIComponent(path)}`);
  const todo = (mine ?? []).filter((c) => c.needs_my_action);

  return (
    <Page back={false} title="" right={user ? <span className="pr-3 text-[14px] text-grey-600">{user.name}님</span> : null}>
      <div className="mt-4">
        <p className="text-[15px] font-semibold text-toss-blue">계약하자</p>
        <h1 className="mt-2 text-[28px] leading-[38px] font-bold">
          계약서를 만들고
          <br />
          간편하게 서명하세요.
        </h1>
        <p className="mt-3 text-[15px] leading-6 text-grey-600">계약서는 내가 보관하고, 계약의 디지털 지문은 누구나 검증할 수 있어요.</p>
      </div>

      <div className="mt-8">
        <Button testid="home-create" onClick={() => start("/create")}>
          + 계약 만들기
        </Button>
      </div>

      {todo.length > 0 && (
        <Card className="mt-4 bg-toss-blue-light" onClick={() => nav(`/contracts/${todo[0].id}`)} testid="home-todo">
          <p className="font-semibold text-toss-blue">
            {todo.some((c) => c.status === "INVITED" || c.status === "SIGNING") ? "내 서명을 기다리는 계약이 있어요" : "작성 중인 계약이 있어요"} ({todo.length}건)
          </p>
          <p className="mt-1 text-[14px] text-grey-700">{todo[0].title} →</p>
        </Card>
      )}

      <Section title="자주 쓰는 계약">
        <div className="grid grid-cols-2 gap-3">
          {QUICK.map((q) => (
            <Card key={q.id} testid={`quick-${q.id}`} onClick={() => start(`/create/template?t=${q.id}`)} className="flex flex-col gap-2">
              <span className="text-[28px]">{q.emoji}</span>
              <span className="text-[16px] font-semibold">{q.name}</span>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="내 계약" right={user && mine && mine.length > 0 ? <button className="text-[14px] text-grey-600" onClick={() => nav("/contracts")}>전체보기</button> : null}>
        {!user ? (
          <Card onClick={() => nav("/login")}>
            <p className="text-grey-600">로그인하면 내 계약을 볼 수 있어요.</p>
          </Card>
        ) : mine === null ? (
          <p className="text-grey-500">불러오는 중…</p>
        ) : mine.length === 0 ? (
          <Card>
            <p className="text-grey-600">아직 계약이 없어요.</p>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {mine.slice(0, 3).map((c) => (
              <Card key={c.id} onClick={() => nav(c.status === "COMPLETED" ? `/contracts/${c.id}/done` : `/contracts/${c.id}`)} className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.title}</p>
                  <p className="mt-0.5 text-[13px] text-grey-500">{c.counterparty ? `${c.counterparty}님과` : "상대방 초대 전"}</p>
                </div>
                <Badge tone={c.status === "COMPLETED" ? "green" : c.needs_my_action ? "blue" : "grey"}>{STATUS_LABEL[c.status]}</Badge>
              </Card>
            ))}
          </div>
        )}
      </Section>

      <Section title="계약 검증">
        <Card testid="home-verify" onClick={() => nav("/verify")} className="flex items-center gap-4">
          <span className="text-[28px]">🔍</span>
          <div>
            <p className="font-semibold">계약서가 바뀌지 않았는지 확인</p>
            <p className="mt-0.5 text-[14px] text-grey-600">PDF 를 올리거나 검증번호를 입력하세요</p>
          </div>
        </Card>
      </Section>
      <LegalFooter />
    </Page>
  );
}
