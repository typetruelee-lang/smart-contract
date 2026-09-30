import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, ErrorView, Loading, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import type { Field, TemplateSummary } from "../lib/types";

export default function TemplatePick() {
  const nav = useNavigate();
  const toast = useToast();
  const [sp] = useSearchParams();
  const [list, setList] = useState<TemplateSummary[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const auto = useRef(false);

  async function pick(id: string) {
    if (busy) return;
    setBusy(true);
    try {
      const t = await api.get<{ title: string; body: string; contract_type: string; fields: Field[] }>(`/api/templates/${id}`);
      const r = await api.post<{ id: string }>("/api/contracts", { title: t.title, source: "TEMPLATE", contract_type: t.contract_type, body_text: t.body, fields: t.fields });
      nav(`/contracts/${r.id}`, { replace: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "템플릿을 불러오지 못했어요.", "error");
      setBusy(false);
    }
  }

  useEffect(() => {
    api
      .get<{ templates: TemplateSummary[] }>("/api/templates")
      .then((r) => setList(r.templates))
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    const t = sp.get("t");
    if (t && list && !auto.current) {
      auto.current = true;
      pick(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, sp]);

  if (err) return <Page title="템플릿 선택"><ErrorView message={err} /></Page>;
  if (!list || busy) return <Page title="템플릿 선택"><Loading label={busy ? "계약서를 준비하고 있어요" : undefined} /></Page>;
  return (
    <Page title="템플릿 선택">
      <p className="mt-2 mb-6 text-[22px] font-bold">어떤 계약인가요?</p>
      <div className="flex flex-col gap-3">
        {list.map((t) => (
          <Card key={t.id} testid={`template-${t.id}`} onClick={() => pick(t.id)}>
            <p className="text-[17px] font-semibold">{t.name}</p>
            <p className="mt-0.5 text-[14px] text-grey-600">{t.subtitle} · {t.title}</p>
            {t.note && (
              <p data-testid={`template-note-${t.id}`} className="mt-2 text-[13px] leading-5 text-grey-500">
                {t.note}
              </p>
            )}
          </Card>
        ))}
      </div>
      <p data-testid="template-notice" className="mt-6 text-[13px] leading-5 text-grey-500">
        템플릿은 일반적인 예시일 뿐 법률 자문이 아니에요. 내 상황에 맞는지, 법에 어긋나는 내용이 없는지는 직접 확인해야 하며, 중요한 계약은 변호사 등 전문가의 검토를 받아 주세요.
      </p>
    </Page>
  );
}
