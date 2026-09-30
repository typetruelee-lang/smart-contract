"""특약·옵션 조항.

- 계약 종류별로 자주 쓰는 특약을 서버가 정해 두고, 사용자는 켜고 끄기만 한다 (클라이언트는 id 만 보냄).
- 조항 한 개 = 본문의 한 줄 `- 조항문`. 조항에 들어가는 값은 `{라벨}` 빈칸(기존 필드 시스템)으로 둔다.
  그래서 미리보기·PDF·해시·버전·서명 무효화가 그대로 동작한다.
- 법에 어긋나 무효가 될 수 있는 조항(근로자 위약금·교육비 반환·경업금지, 보증인 서명 없는 연대보증 등)은 넣지 않는다.
  값 범위가 법으로 정해진 곳(지연손해금 20%, 수습 임금 90% 이상 등)은 입력 범위로 막는다.
주의: 조항 문구는 일반적인 예시이며 법률 자문을 대체하지 않는다 (LEGAL_REVIEW_CHECKLIST.md).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.fields import FieldSpec

EMPLOYMENT = ("employment", "employment_daily", "employment_parttime")
MAX_CUSTOM = 10
MAX_CUSTOM_LEN = 300
SECTION_TITLE = "특약사항"
FREE_PLACEHOLDER = "{특약사항}"


class ClauseError(ValueError):
    pass


def P(label, type="TEXT", options=None, validation=None):  # noqa: A002
    return {"label": label, "type": type, "assignee": "A", "required": True, "options": options or [], "validation": validation or {}}


# applies_to: contract_type 또는 템플릿 id. "*" 는 모든 계약.
CLAUSES: list[dict[str, Any]] = [
    # ---- 공통 ----
    {"id": "court", "applies_to": ["*"], "title": "관할 법원",
     "text": "이 계약에 관한 분쟁은 {관할법원}을 제1심 관할 법원으로 한다.", "params": [P("관할법원")]},
    {"id": "amend_in_writing", "applies_to": ["*"], "title": "변경은 서면 합의로만",
     "text": "이 계약의 변경은 양 당사자가 서면(전자문서를 포함한다)으로 합의한 경우에만 효력이 있다.", "params": []},
    {"id": "confidential", "applies_to": ["*"], "title": "비밀유지",
     "text": "당사자는 이 계약으로 알게 된 상대방의 정보를 상대방의 동의 없이 제3자에게 누설하지 않는다.", "params": []},
    {"id": "notice", "applies_to": ["*"], "title": "통지 방법",
     "text": "이 계약에 관한 통지는 계약서에 적힌 연락처로 문자메시지 또는 전자우편을 보내는 방법으로 할 수 있다.", "params": []},
    # ---- 차용증 ----
    {"id": "loan_late_interest", "applies_to": ["loan"], "title": "지연손해금",
     "text": "을이 상환일까지 갚지 않으면 상환일 다음 날부터 다 갚는 날까지 연 {지연손해금률}%의 지연손해금을 지급한다.",
     "params": [P("지연손해금률", "NUMBER", validation={"min": 0, "max": 20})],
     "caution": "이자제한법상 최고이자율(연 20%)을 넘을 수 없어요."},
    {"id": "loan_installment", "applies_to": ["loan"], "title": "분할상환",
     "text": "을은 원금을 {분할 횟수}회로 나누어 매월 {매월 상환일}일에 갚는다.",
     "params": [P("분할 횟수", "NUMBER", validation={"min": 2, "max": 120}), P("매월 상환일", "NUMBER", validation={"min": 1, "max": 31})]},
    {"id": "loan_interest_day", "applies_to": ["loan"], "title": "이자 지급일",
     "text": "이자는 매월 {이자 지급일}일에 지급한다.", "params": [P("이자 지급일", "NUMBER", validation={"min": 1, "max": 31})]},
    {"id": "loan_prepay", "applies_to": ["loan"], "title": "조기상환 허용",
     "text": "을은 상환일 전에도 언제든지 원금의 전부 또는 일부를 갚을 수 있으며, 이 경우 이자는 실제로 빌린 기간만큼만 계산한다.", "params": []},
    # ---- 용역 ----
    {"id": "svc_advance", "applies_to": ["service"], "title": "선급금",
     "text": "갑은 {선급금 지급일}까지 용역 대금 중 {선급금}원을 먼저 지급하고, 나머지는 검수 완료 후 지급한다.",
     "params": [P("선급금", "NUMBER"), P("선급금 지급일", "DATE")]},
    {"id": "svc_copyright", "applies_to": ["service"], "title": "저작권 귀속",
     "text": "결과물의 저작재산권은 대금 전액이 지급된 때에 갑에게 이전된다. 다만 을은 결과물을 자신의 포트폴리오로 사용할 수 있다.", "params": []},
    {"id": "svc_revisions", "applies_to": ["service"], "title": "무상 수정 횟수",
     "text": "검수 과정에서 을은 {무상 수정 횟수}회까지 무상으로 수정하며, 그 이후의 수정은 별도로 협의한다.",
     "params": [P("무상 수정 횟수", "NUMBER", validation={"min": 0, "max": 50})]},
    {"id": "svc_delay_penalty", "applies_to": ["service"], "title": "지체상금",
     "text": "을이 기한까지 용역을 완료하지 못하면 지체 1일마다 대금의 {지체상금률}%를 지체상금으로 지급한다. 다만 지체상금 총액은 대금의 10%를 넘지 않는다.",
     "params": [P("지체상금률", "NUMBER", validation={"min": 0, "max": 1})],
     "caution": "지나치게 많은 지체상금은 법원이 줄일 수 있어요(민법 제398조)."},
    {"id": "svc_warranty", "applies_to": ["service"], "title": "하자보수",
     "text": "을은 검수 완료 후 {하자보수 기간}일 동안 결과물의 하자를 무상으로 보수한다.",
     "params": [P("하자보수 기간", "NUMBER", validation={"min": 1, "max": 3650})]},
    # ---- 거래 ----
    {"id": "goods_deposit", "applies_to": ["goods"], "title": "계약금",
     "text": "을은 계약 체결 시 계약금 {계약금}원을 지급하고 잔금은 인도할 때 지급한다. 중도금이나 잔금을 치르기 전까지 을은 계약금을 포기하고, 갑은 그 두 배를 돌려주고 계약을 해제할 수 있다.",
     "params": [P("계약금", "NUMBER")], "caution": "민법 제565조(해약금)에 따른 문구예요."},
    {"id": "goods_shipping", "applies_to": ["goods"], "title": "배송비 부담",
     "text": "물품의 배송비는 {배송비 부담자}가 부담한다.", "params": [P("배송비 부담자", "SELECT", options=["매도인(갑)", "매수인(을)"])]},
    {"id": "goods_title", "applies_to": ["goods"], "title": "소유권 이전 시점",
     "text": "물품의 소유권은 갑이 대금 전액을 받은 때에 을에게 이전된다.", "params": []},
    {"id": "goods_as_is", "applies_to": ["goods"], "title": "중고 현상태 거래",
     "text": "을은 물품의 현재 상태를 확인하였고, 갑이 미리 알린 하자({고지한 하자})에 대해서는 책임을 묻지 않는다.",
     "params": [P("고지한 하자")], "caution": "매도인이 알고도 알리지 않은 하자까지 면책되지는 않아요(민법 제584조)."},
    {"id": "goods_defect_notice", "applies_to": ["goods"], "title": "하자 통지 기간",
     "text": "을은 물품을 받은 날부터 {하자 통지 기간}일 이내에 하자를 알려야 교환 또는 환불을 요구할 수 있다.",
     "params": [P("하자 통지 기간", "NUMBER", validation={"min": 1, "max": 365})]},
    # ---- 근로계약 (3종 공통) ----
    {"id": "emp_secret", "applies_to": list(EMPLOYMENT), "title": "영업비밀 보호",
     "text": "근로자는 재직 중 및 퇴직 후 {비밀유지 기간}년간 업무상 알게 된 회사의 영업비밀을 누설하지 않는다.",
     "params": [P("비밀유지 기간", "NUMBER", validation={"min": 1, "max": 5})]},
    {"id": "emp_meal", "applies_to": list(EMPLOYMENT), "title": "식대 지급",
     "text": "사업주는 매월 식대 {식대}원을 임금과 함께 지급한다.", "params": [P("식대", "NUMBER")]},
    {"id": "emp_relocate", "applies_to": ["employment", "employment_parttime"], "title": "근무장소 변경",
     "text": "업무상 필요한 경우 사업주는 근로자와 협의하여 근무장소를 변경할 수 있다.", "params": []},
    {"id": "emp_probation", "applies_to": ["employment"], "title": "수습기간",
     "text": "근로개시일부터 {수습 기간}개월은 수습기간으로 하며, 수습기간 중 임금은 정상 임금의 {수습 임금 비율}%로 한다.",
     "params": [P("수습 기간", "NUMBER", validation={"min": 1, "max": 3}), P("수습 임금 비율", "NUMBER", validation={"min": 90, "max": 100})],
     "caution": "최저임금 감액은 1년 이상 계약·수습 3개월 이내만 가능하고, 단순노무직은 감액할 수 없어요(최저임금법 제5조)."},
    {"id": "part_overtime", "applies_to": ["employment_parttime"], "title": "초과근로",
     "text": "사업주는 근로자의 동의를 얻은 경우에만 소정근로시간을 초과하여 근로하게 할 수 있으며, 그 시간은 1주 12시간을 넘지 않는다.", "params": [],
     "caution": "기간제 및 단시간근로자 보호 등에 관한 법률 제6조."},
    {"id": "daily_idle", "applies_to": ["employment_daily"], "title": "작업 중지 시 휴업수당",
     "text": "사업주의 사정으로 일을 하지 못한 날에는 근로기준법 제46조에 따라 휴업수당을 지급한다.", "params": []},
]
BY_ID = {c["id"]: c for c in CLAUSES}
# 넣지 않는 조항과 이유 (문서·화면 안내용)
EXCLUDED = {
    "근로자 위약금·교육비 반환 약정": "근로기준법 제20조(위약 예정의 금지)에 어긋나 무효가 될 수 있어요.",
    "근로자 경업금지": "직업 선택의 자유를 지나치게 제한하면 무효가 될 수 있어 개별 검토가 필요해요.",
    "연대보증": "보증인의 서명과 보증 최고액 기재가 필요해 두 사람 계약서로는 효력이 없을 수 있어요(보증인 보호를 위한 특별법 제3조).",
}


def _applies(c: dict, contract_type: str, template_id: str | None) -> bool:
    # 근로계약 3종은 contract_type 이 같으므로(employment) 템플릿 id 로 구분한다
    from app.services import catalog
    key = template_id if template_id in catalog.TEMPLATES else contract_type
    a = c["applies_to"]
    return "*" in a or key in a


def available(contract_type: str, template_id: str | None = None) -> list[dict]:
    """계약 종류(와 템플릿)에 맞는 조항 목록. 종류별 조항이 먼저, 공통 조항이 뒤."""
    items = [c for c in CLAUSES if _applies(c, contract_type, template_id)]
    items.sort(key=lambda c: "*" in c["applies_to"])
    return [{"id": c["id"], "title": c["title"], "text": c["text"], "preview": re.sub(r"\{[^{}]+\}", "___", c["text"]),
             "caution": c.get("caution"), "common": "*" in c["applies_to"], "params": [p["label"] for p in c["params"]]} for c in items]


def line_of(clause_id: str) -> str:
    return "- " + BY_ID[clause_id]["text"]


def clean_custom(text: str) -> str:
    s = re.sub(r"[{}<>]", "", str(text)).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        raise ClauseError("특약 내용을 입력해 주세요.")
    if len(s) > MAX_CUSTOM_LEN:
        raise ClauseError(f"특약 한 개는 {MAX_CUSTOM_LEN}자 이하로 입력해 주세요.")
    return s


def apply_clauses(payload: dict, contract_type: str, template_id: str | None, library_ids: list[str], custom_texts: list[str]) -> dict:
    """선택 상태를 본문·빈칸에 반영한 새 (body_text, fields, clauses, custom_clauses) 를 돌려준다. 멱등."""
    ids: list[str] = []
    for cid in library_ids:
        if cid not in BY_ID or not _applies(BY_ID[cid], contract_type, template_id):
            raise ClauseError("이 계약서에 넣을 수 없는 특약이에요.")
        if cid not in ids:
            ids.append(cid)
    custom: list[str] = []
    for t in custom_texts:
        s = clean_custom(t)
        if s not in custom:
            custom.append(s)
    if len(custom) > MAX_CUSTOM:
        raise ClauseError(f"직접 쓴 특약은 {MAX_CUSTOM}개까지 넣을 수 있어요.")

    body = payload.get("body_text") or ""
    # 1) 이전에 넣은 특약 줄을 모두 뺀다 (지금 선택과 관계없이) — 줄 문구가 고정이라 정확히 찾을 수 있다
    old_lines = {line_of(c) for c in payload.get("clauses", []) if c in BY_ID} | {"- " + t for t in payload.get("custom_clauses", [])}
    lines = [ln for ln in body.split("\n") if ln not in old_lines]
    had_section = any(ln.strip() == SECTION_TITLE for ln in lines)
    # 2) 새 특약 줄을 {특약사항} 줄 바로 위(없으면 본문 끝 '특약사항' 제목 아래)에 넣는다
    new_lines = [line_of(c) for c in ids] + ["- " + t for t in custom]
    if new_lines:
        at = next((i for i, ln in enumerate(lines) if ln.strip() == FREE_PLACEHOLDER), None)
        if at is None:
            sec = next((i for i, ln in enumerate(lines) if ln.strip() == SECTION_TITLE), None)
            if sec is None:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines += ["", SECTION_TITLE]
                sec = len(lines) - 1
            at = sec + 1
        lines[at:at] = new_lines
    # 특약을 모두 끄면 앱이 붙였던 빈 '특약사항' 제목도 정리
    if not new_lines and payload.get("clauses_section_added"):
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == SECTION_TITLE:
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
    body_text = "\n".join(lines)

    # 3) 빈칸: 꺼진 조항 전용 빈칸은 빼고, 새로 켠 조항 빈칸은 추가 (켜 둔 조항의 값은 유지)
    old_param_labels = {p["label"] for c in payload.get("clauses", []) if c in BY_ID for p in BY_ID[c]["params"]}
    want = {p["label"]: p for c in ids for p in BY_ID[c]["params"]}
    fields = [f for f in payload.get("fields", []) if not (f["label"] in old_param_labels and f["label"] not in want)]
    have = {f["label"] for f in fields}
    for label, p in want.items():
        if label not in have:
            fields.append(FieldSpec(**p).model_dump())
    return {"body_text": body_text, "fields": fields, "clauses": ids, "custom_clauses": custom,
            "clauses_section_added": bool(new_lines) and (payload.get("clauses_section_added") or (not had_section and FREE_PLACEHOLDER not in body))}
