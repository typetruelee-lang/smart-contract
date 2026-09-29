import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Card, ErrorView, Loading, Page } from "../components/ui";
import { api } from "../lib/api";
import { ANCHOR_LABEL, STATUS_LABEL, formatKst } from "../lib/format";
import type { ContractSummary } from "../lib/types";

export default function MyContracts() {
  const nav = useNavigate();
  const [list, setList] = useState<ContractSummary[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get<{ contracts: ContractSummary[] }>("/api/contracts").then((r) => setList(r.contracts)).catch((e) => setErr(e.message));
  }, []);
  if (err) return <Page title="내 계약"><ErrorView message={err} /></Page>;
  if (!list) return <Page title="내 계약"><Loading /></Page>;
  return (
    <Page title="내 계약">
      {list.length === 0 ? (
        <p className="mt-10 text-center text-grey-500">아직 계약이 없어요.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {list.map((c) => (
            <Card key={c.id} onClick={() => nav(c.status === "COMPLETED" ? `/contracts/${c.id}/done` : `/contracts/${c.id}`)}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-semibold">{c.title}</p>
                <Badge tone={c.status === "COMPLETED" ? "green" : c.needs_my_action ? "blue" : "grey"}>{STATUS_LABEL[c.status]}</Badge>
              </div>
              <p className="mt-1 text-[13px] text-grey-500">
                {c.counterparty ? `${c.counterparty}님` : "상대방 없음"} · {formatKst(c.completed_at ?? c.created_at)}
                {c.anchor_status !== "NOT_REQUESTED" && ` · 블록체인 ${ANCHOR_LABEL[c.anchor_status]}`}
              </p>
            </Card>
          ))}
        </div>
      )}
    </Page>
  );
}
