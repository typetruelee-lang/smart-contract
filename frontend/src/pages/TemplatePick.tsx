import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorView, Loading, Page, useToast } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { lookOf } from "../lib/templates";
import type { Field, TemplateSummary } from "../lib/types";

function Chevron() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 text-grey-300">
      <path d="M9 5l7 7-7 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Icon({ id, size = "h-12 w-12 text-[24px]" }: { id: string; size?: string }) {
  const l = lookOf(id);
  return <span aria-hidden="true" className={`grid shrink-0 place-items-center rounded-2xl ${size} ${l.tint}`}>{l.icon}</span>;
}

export default function TemplatePick() {
  const nav = useNavigate();
  const toast = useToast();
  const loc = useLocation();
  const [sp] = useSearchParams();
  const [list, setList] = useState<TemplateSummary[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const auto = useRef(false);
  const workRef = useRef<HTMLElement>(null);

  async function pick(id: string) {
    if (busy) return;
    setBusy(true);
    try {
      const t = await api.get<{ title: string; body: string; contract_type: string; fields: Field[] }>(`/api/templates/${id}`);
      const r = await api.post<{ id: string }>("/api/contracts", { title: t.title, source: "TEMPLATE", contract_type: t.contract_type, body_text: t.body, fields: t.fields, template_id: id });
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

  // 홈의 '근로계약서' 에서 들어오면 근로계약서 묶음으로 바로 이동
  useEffect(() => {
    if (list && loc.hash === "#employment") workRef.current?.scrollIntoView({ block: "start" });
  }, [list, loc.hash]);

  if (err) return <Page title="템플릿 선택"><ErrorView message={err} /></Page>;
  if (!list || busy) return <Page title="템플릿 선택"><Loading label={busy ? "계약서를 준비하고 있어요" : undefined} /></Page>;

  const everyday = list.filter((t) => t.group !== "employment");
  const work = list.filter((t) => t.group === "employment");

  return (
    <Page title="템플릿 선택">
      <p className="mt-2 text-[24px] leading-[34px] font-bold">어떤 계약인가요?</p>
      <p className="mt-1 text-[15px] text-grey-600">고르면 빈칸만 채우면 되는 계약서가 바로 만들어져요.</p>

      <section className="mt-7" aria-labelledby="grp-everyday">
        <h2 id="grp-everyday" className="mb-3 text-[15px] font-semibold text-grey-600">자주 쓰는 계약</h2>
        <div className="flex flex-col gap-2.5">
          {everyday.map((t) => (
            <button key={t.id} data-testid={`template-${t.id}`} onClick={() => pick(t.id)}
              className="flex w-full items-center gap-4 rounded-3xl bg-grey-50 px-5 py-4 text-left transition duration-150 ease-out active:scale-[0.98] active:bg-grey-100">
              <Icon id={t.id} />
              <span className="min-w-0 flex-1">
                <span className="block text-[17px] font-semibold">{t.name}</span>
                <span className="mt-0.5 block text-[14px] text-grey-600">{t.subtitle}</span>
              </span>
              <Chevron />
            </button>
          ))}
        </div>
      </section>

      <section ref={workRef} id="employment" className="mt-9 scroll-mt-16" aria-labelledby="grp-employment">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 id="grp-employment" className="text-[15px] font-semibold text-grey-600">근로계약서</h2>
          <span className="text-[13px] text-grey-500">고용노동부 표준 서식</span>
        </div>
        <div className="overflow-hidden rounded-3xl border border-grey-100 bg-white shadow-[0_2px_12px_rgba(0,27,55,0.05)]">
          {work.map((t, i) => (
            <div key={t.id} className={i > 0 ? "border-t border-grey-100" : ""}>
              <button data-testid={`template-${t.id}`} onClick={() => pick(t.id)}
                className="flex w-full items-center gap-4 px-5 pt-4 pb-2 text-left transition duration-150 ease-out active:bg-grey-50">
                <Icon id={t.id} size="h-11 w-11 text-[22px]" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[16px] font-semibold">{t.name}</span>
                  <span className="mt-0.5 block text-[13px] text-grey-600">{t.subtitle}</span>
                </span>
                <Chevron />
              </button>
              {t.note && (
                <details className="group px-5 pb-4 pl-[80px]">
                  <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-lg py-1 text-[13px] font-medium text-toss-blue [&::-webkit-details-marker]:hidden">
                    작성 전 확인할 점
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="transition-transform duration-200 group-open:rotate-180">
                      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </summary>
                  <p data-testid={`template-note-${t.id}`} className="mt-1.5 rounded-2xl bg-grey-50 p-3.5 text-[13px] leading-5 text-grey-600">
                    {t.note}
                  </p>
                </details>
              )}
            </div>
          ))}
        </div>
      </section>

      <p data-testid="template-notice" className="mt-8 mb-4 text-[13px] leading-5 text-grey-500">
        템플릿은 일반적인 예시일 뿐 법률 자문이 아니에요. 내 상황에 맞는지, 법에 어긋나는 내용이 없는지는 직접 확인해야 하며, 중요한 계약은 변호사 등 전문가의 검토를 받아 주세요.
      </p>
    </Page>
  );
}
