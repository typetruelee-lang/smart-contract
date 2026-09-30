"""특약·옵션 API: 본문·PDF 반영, 버전·서명 무효화, 권한."""
import io

from pypdf import PdfReader

from app.services import catalog, clauses
from tests.conftest import create_text_contract, sign


def _create_loan(a):
    t = catalog.get_template("loan")
    r = a.post("/api/contracts", {"title": t["title"], "source": "TEMPLATE", "contract_type": t["contract_type"], "body_text": t["body"],
                                  "fields": t["fields"], "template_id": "loan"})
    assert r.status_code == 200, r.text
    return r.json()["id"]




def _ready_text_contract(a):
    cid, fields = create_text_contract(a)
    by = {f["label"]: f for f in fields}
    a.put(f"/api/contracts/{cid}/values", {"values": {by["대여금액"]["field_id"]: "5000000", by["채권자"]["field_id"]: "홍길동",
                                                        by["채무자"]["field_id"]: "김철수", by["상환일"]["field_id"]: "2027-01-31", by["이자율"]["field_id"]: "3"}})
    return cid


def test_list_endpoint(client_factory):
    a = client_factory()
    r = a.get("/api/clauses?contract_type=employment&template_id=employment_parttime").json()
    ids = [c["id"] for c in r["clauses"]]
    assert "part_overtime" in ids and "emp_probation" not in ids and "court" in ids
    assert ids.index("part_overtime") < ids.index("court")  # 종류별 조항이 먼저
    assert all("{" not in c["preview"] for c in r["clauses"]) and r["excluded"]


def test_set_clauses_updates_body_fields_and_pdf(client_factory):
    a = client_factory()
    a.login("hong")
    cid = _create_loan(a)
    r = a.put(f"/api/contracts/{cid}/clauses", {"library": ["loan_late_interest", "court"], "custom": ["반려동물 관련 비용은 을이 부담한다"]})
    assert r.status_code == 200, r.text
    view = a.get(f"/api/contracts/{cid}").json()
    p = view["payload"]
    assert p["clauses"] == ["loan_late_interest", "court"] and p["custom_clauses"] == ["반려동물 관련 비용은 을이 부담한다"]
    assert p["template_id"] == "loan" and clauses.line_of("court") in p["body_text"]
    by = {f["label"]: f for f in p["fields"]}
    bad = a.put(f"/api/contracts/{cid}/values", {"values": {by["지연손해금률"]["field_id"]: "25"}})
    assert bad.status_code == 422 and "20" in bad.json()["detail"]["message"]
    ok = a.put(f"/api/contracts/{cid}/values", {"values": {by["지연손해금률"]["field_id"]: "15", by["관할법원"]["field_id"]: "서울중앙지방법원"}})
    assert ok.status_code == 200
    pdf = a.get(f"/api/contracts/{cid}/pdf/preview").content
    text = "".join(pg.extract_text() for pg in PdfReader(io.BytesIO(pdf)).pages).replace("\n", "")
    assert "서울중앙지방법원" in text and "반려동물" in text and "지연손해금" in text
    # 같은 선택을 다시 보내면 새 버전이 생기지 않는다
    v1 = a.get(f"/api/contracts/{cid}").json()["current_version_no"]
    a.put(f"/api/contracts/{cid}/clauses", {"library": ["loan_late_interest", "court"], "custom": ["반려동물 관련 비용은 을이 부담한다"]})
    assert a.get(f"/api/contracts/{cid}").json()["current_version_no"] == v1


def test_invalid_clause_rejected_and_only_owner(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    assert a.put(f"/api/contracts/{_create_loan(a)}/clauses", {"library": ["emp_probation"]}).status_code == 422
    cid = _ready_text_contract(a)
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    assert b.put(f"/api/contracts/{cid}/clauses", {"library": ["court"]}).status_code == 403


def test_changing_clauses_after_signature_invalidates_it(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid = _ready_text_contract(a)
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    sign(b, cid)
    r = a.put(f"/api/contracts/{cid}/clauses", {"library": ["confidential"], "custom": []})
    assert r.status_code == 200 and r.json()["version_no"] == 2
    view = a.get(f"/api/contracts/{cid}").json()
    assert next(p for p in view["parties"] if p["role"] == "B")["signature_status"] == "INVALIDATED"
    assert "특약사항" in view["payload"]["body_text"] and view["versions"][-1]["reason"] == "특약 변경"
