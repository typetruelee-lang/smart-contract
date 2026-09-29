"""test-results/raw/* → test-results/summary.json"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "test-results" / "raw"


def load(name, default=None):
    p = RAW / name
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


status = dict(line.strip().split("=", 1) for line in (RAW / "status.env").read_text().splitlines() if "=" in line)
suites = {}

# backend (JUnit)
if (RAW / "backend.xml").exists():
    r = ET.parse(RAW / "backend.xml").getroot()
    ts = r if r.tag == "testsuite" else r.find("testsuite")
    total, fails, errs, skip = (int(ts.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
    suites["backend (pytest)"] = {"passed": total - fails - errs - skip, "failed": fails + errs, "skipped": skip}

# frontend (vitest json)
fj = load("frontend.json")
if fj:
    suites["frontend (vitest)"] = {"passed": fj.get("numPassedTests", 0), "failed": fj.get("numFailedTests", 0), "skipped": fj.get("numPendingTests", 0)}

# e2e (playwright json)
ej = load("e2e.json")
if ej:
    per = {}
    def walk(s, project_hint=None):
        for spec in s.get("specs", []):
            for t in spec.get("tests", []):
                proj = t.get("projectName", "e2e")
                st = t.get("status")  # expected | unexpected | skipped | flaky
                d = per.setdefault(proj, {"passed": 0, "failed": 0, "skipped": 0})
                d["passed" if st in ("expected", "flaky") else "skipped" if st == "skipped" else "failed"] += 1
        for sub in s.get("suites", []):
            walk(sub)
    for s in ej.get("suites", []):
        walk(s)
    for proj, d in per.items():
        suites[f"e2e-{proj} (playwright)"] = d

bandit = load("bandit.json", {}) or {}
sev = [x.get("issue_severity") for x in bandit.get("results", [])]
pa = load("pip-audit.json", {}) or {}
pip_vulns = sum(len(d.get("vulns", [])) for d in pa.get("dependencies", []))
na = load("npm-audit.json", {}) or {}
nv = (na.get("metadata") or {}).get("vulnerabilities") or {}
ss = load("secret-scan.json", {}) or {}

visual_md = ROOT / "FINAL_REVIEW" / "VISUAL_REVIEW.md"
visual_ok = False
if visual_md.exists():
    t = visual_md.read_text()
    rows_ok = len(re.findall(r"\|\s*OK\s*\|", t))
    rows_bad = len(re.findall(r"\|\s*(FIX|FAIL)\s*\|", t))
    shots = len(list((ROOT / "FINAL_REVIEW").glob("*.png")))
    visual_ok = rows_ok >= 12 and rows_bad == 0 and shots >= 12

summary = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "suites": suites,
    "passed": sum(s["passed"] for s in suites.values()),
    "failed": sum(s["failed"] for s in suites.values()),
    "skipped": sum(s.get("skipped", 0) for s in suites.values()),
    "typecheck_ok": status.get("typecheck_exit") == "0",
    "build_ok": status.get("web_build_exit") == "0" and status.get("typecheck_exit") == "0",
    "ait_build_ok": status.get("ait_build_exit") == "0",
    "contract_compile_ok": status.get("contract_compile_exit") == "0",
    "visual_review_ok": visual_ok,
    "security": {
        "bandit_high": sev.count("HIGH"), "bandit_medium": sev.count("MEDIUM"), "bandit_low": sev.count("LOW"),
        "pip_audit_vulnerabilities": pip_vulns,
        "npm_audit": {k: nv.get(k, 0) for k in ("critical", "high", "moderate", "low")},
        "secret_scan_findings": len(ss.get("findings", [])),
    },
    "exit_codes": status,
}
out = ROOT / "test-results" / "summary.json"
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps({k: summary[k] for k in ("passed", "failed", "build_ok", "ait_build_ok", "visual_review_ok")}, ensure_ascii=False))
for name, s in suites.items():
    print(f"  {name:32s} PASS {s['passed']:4d}  FAIL {s['failed']:3d}")
print("  security:", summary["security"])
