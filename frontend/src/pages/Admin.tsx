import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, ErrorView, Loading, Page, Row } from "../components/ui";
import { api } from "../lib/api";

interface Status {
  environment: string;
  components: Record<string, { ok: boolean; detail: unknown; ms: number }>;
  providers: Record<string, { requested: string; active: string; fallback: boolean; reason: string }>;
  anchor_jobs: Record<string, number>;
  tests: null | { passed: number; failed: number; skipped?: number; generated_at: string; suites: Record<string, { passed: number; failed: number; skipped?: number }>; visual_review_ok?: boolean; build_ok?: boolean };
  security: { warnings: string[] };
  readiness: { development_complete: boolean; production_ready: boolean; production_blockers: string[] };
  config: { blockchain_enabled: boolean; blockchain_price: number; anchor_mode: string };
}

export default function Admin() {
  const [s, setS] = useState<Status | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    setErr("");
    api.get<Status>("/api/admin/status").then(setS).catch((e) => setErr(e.message));
  }, []);
  useEffect(load, [load]);

  async function runWorkers() {
    setBusy(true);
    try {
      await api.post("/api/admin/workers/run");
      load();
    } finally {
      setBusy(false);
    }
  }

  if (err) return <Page title="System Status"><ErrorView message={err} onRetry={load} /></Page>;
  if (!s) return <Page title="System Status"><Loading /></Page>;
  const t = s.tests;
  return (
    <Page title="System Status" back={false}>
      <div className="grid grid-cols-2 gap-2" data-testid="readiness">
        <Card className="p-4">
          <p className="text-[12px] text-grey-500">DEVELOPMENT</p>
          <p className={`mt-1 text-[16px] font-bold ${s.readiness.development_complete ? "text-ok" : "text-warn"}`}>{s.readiness.development_complete ? "COMPLETE" : "INCOMPLETE"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-[12px] text-grey-500">PRODUCTION</p>
          <p className={`mt-1 text-[16px] font-bold ${s.readiness.production_ready ? "text-ok" : "text-[#d97706]"}`}>{s.readiness.production_ready ? "READY" : "NOT READY"}</p>
        </Card>
      </div>

      <h2 className="mt-6 mb-2 text-[17px] font-bold">Components</h2>
      <Card className="p-4" testid="components">
        {Object.entries(s.components).map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-3 border-b border-grey-100 py-2 last:border-0">
            <span className="font-medium">{k}</span>
            <span className="text-right text-[13px]">
              <span className={v.ok ? "font-bold text-ok" : "font-bold text-warn"}>{v.ok ? "✓" : "✗"}</span>{" "}
              <span className="text-grey-500">{typeof v.detail === "string" ? v.detail : JSON.stringify(v.detail)}</span>
            </span>
          </div>
        ))}
      </Card>

      <h2 className="mt-6 mb-2 text-[17px] font-bold">Tests</h2>
      <Card className="p-4" testid="tests">
        {t ? (
          <>
            <Row label="Passed"><span className="text-ok">{t.passed}</span></Row>
            <Row label="Failed"><span className={t.failed ? "text-warn" : ""}>{t.failed}</span></Row>
            {Object.entries(t.suites).map(([k, v]) => <Row key={k} label={k}>{v.passed} / {v.passed + v.failed}{v.failed ? ` (실패 ${v.failed})` : ""}</Row>)}
            <Row label="화면 검수">{t.visual_review_ok ? "PASS" : "미완료"}</Row>
            <Row label="Build">{t.build_ok ? "PASS" : "미확인"}</Row>
            <Row label="실행 시각">{t.generated_at}</Row>
          </>
        ) : (
          <p className="text-grey-500">아직 테스트 결과가 없어요. <code>make test</code> 를 실행하세요.</p>
        )}
      </Card>

      <h2 className="mt-6 mb-2 text-[17px] font-bold">Providers</h2>
      <Card className="p-4">
        {Object.entries(s.providers).map(([k, v]) => (
          <Row key={k} label={k}>{v.active} {v.active === "mock" || v.active === "local" ? <Badge tone="orange">개발용</Badge> : <Badge tone="green">운영</Badge>}</Row>
        ))}
      </Card>

      <h2 className="mt-6 mb-2 text-[17px] font-bold">Security</h2>
      <Card className="p-4" testid="security">
        <Row label="Warnings">{s.security.warnings.length}</Row>
        {s.security.warnings.map((w) => <p key={w} className="text-[13px] text-warn">· {w}</p>)}
      </Card>

      <h2 className="mt-6 mb-2 text-[17px] font-bold">Environment</h2>
      <Card className="p-4">
        <Row label="APP_ENV">{s.environment}</Row>
        <Row label="블록체인 기능">{s.config.blockchain_enabled ? `ON · ${s.config.blockchain_price}원 · ${s.config.anchor_mode}` : "OFF"}</Row>
        <Row label="Anchor jobs">{JSON.stringify(s.anchor_jobs)}</Row>
      </Card>
      {s.readiness.production_blockers.length > 0 && (
        <Card className="mt-4 p-4">
          <p className="mb-1 font-semibold">운영 전환 전 남은 항목</p>
          {s.readiness.production_blockers.map((b) => <p key={b} className="text-[13px] text-grey-600">· {b}</p>)}
        </Card>
      )}
      <div className="mt-6"><Button variant="secondary" onClick={runWorkers} loading={busy}>워커 즉시 실행 (재시도/보존정책)</Button></div>
    </Page>
  );
}
