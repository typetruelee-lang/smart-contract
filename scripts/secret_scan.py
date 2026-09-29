"""Git 에 올라가는 파일에서 비밀값(개인키, API 키, 비밀번호 하드코딩)을 찾는다."""
import json
import re
import subprocess
import sys

PATTERNS = {
    "private_key_block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "eth_private_key": re.compile(r"(?i)(private[_-]?key|PRIVATE_KEY)\s*[=:]\s*['\"]?0x[0-9a-fA-F]{64}"),
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_secret": re.compile(r"(?i)(secret|api[_-]?key|password|token)\s*[=:]\s*['\"][A-Za-z0-9_\-+/=]{24,}['\"]"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}
ALLOW = ("package-lock.json", ".png", ".pdf", ".ait", "artifacts/DocumentRegistry.json")

files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True, check=True).stdout.split()
findings = []
for f in files:
    if f.endswith(ALLOW):
        continue
    try:
        text = open(f, encoding="utf-8", errors="ignore").read()
    except (IsADirectoryError, FileNotFoundError):
        continue
    for name, pat in PATTERNS.items():
        for m in pat.finditer(text):
            findings.append({"file": f, "rule": name, "line": text[: m.start()].count("\n") + 1})
tracked_env = [f for f in files if re.search(r"(^|/)\.env(\.local)?$", f)]
for f in tracked_env:
    findings.append({"file": f, "rule": "env_file_tracked", "line": 0})
print(json.dumps({"files_scanned": len(files), "findings": findings}, ensure_ascii=False, indent=2))
sys.exit(1 if findings else 0)
