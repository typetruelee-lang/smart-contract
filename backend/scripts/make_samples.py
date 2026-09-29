"""테스트/체험용 샘플 PDF 생성: samples/sample-text-contract.pdf, samples/sample-scanned-contract.pdf"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.fixtures.pdfs import write_samples  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "samples")
write_samples(out)
print("wrote", out)
