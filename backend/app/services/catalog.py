"""자주 쓰는 계약 템플릿 4종.

본문에는 `{라벨}` 자리표시자를 쓰고, 각 자리표시자의 입력 유형/담당자를 fields 로 정의한다.
주의: 템플릿 문구는 일반적인 예시이며 법률 자문을 대체하지 않는다 (LEGAL_REVIEW_CHECKLIST.md).
"""
from __future__ import annotations

from app.services.fields import FieldSpec


def F(label, type="TEXT", assignee="A", required=True, options=None):  # noqa: A002
    return {"label": label, "type": type, "assignee": assignee, "required": required, "options": options or []}


TEMPLATES: dict[str, dict] = {
    "loan": {
        "id": "loan", "name": "차용증", "subtitle": "돈을 빌리고 빌려줄 때", "contract_type": "loan",
        "title": "금전소비대차계약서",
        "body": """채권자 {채권자 이름}(이하 "갑")과 채무자 {채무자 이름}(이하 "을")은 다음과 같이 금전소비대차계약을 체결한다.

제1조 (대여금)
갑은 을에게 금 {대여금액} 원을 빌려주고, 을은 이를 틀림없이 받았다.

제2조 (이자)
이자는 연 {이자율} %로 한다.

제3조 (상환)
을은 {상환일}까지 원금과 이자를 갑에게 갚는다.
상환 방법: {상환 방법}

제4조 (특약사항)
{특약사항}

채권자(갑) 연락처: {채권자 연락처}
채무자(을) 연락처: {채무자 연락처}

채권자(갑) {채권자 이름} {채권자 서명}
채무자(을) {채무자 이름} {채무자 서명}""",
        "fields": [
            F("채권자 이름"), F("채무자 이름", assignee="B"), F("대여금액", "NUMBER"), F("이자율", "NUMBER"),
            F("상환일", "DATE"), F("상환 방법", "SELECT", options=["계좌이체", "현금", "기타"]),
            F("특약사항", "LONG_TEXT", required=False), F("채권자 연락처", "PHONE"), F("채무자 연락처", "PHONE", assignee="B"),
            F("채권자 서명", "SIGNATURE"), F("채무자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "service": {
        "id": "service", "name": "용역계약", "subtitle": "일을 맡기고 맡을 때", "contract_type": "service",
        "title": "용역계약서",
        "body": """발주자 {발주자 이름}(이하 "갑")과 수행자 {수행자 이름}(이하 "을")은 아래 용역에 관하여 계약을 체결한다.

제1조 (용역 내용)
{용역 내용}

제2조 (기간)
용역 기간은 {시작일}부터 {종료일}까지로 한다.

제3조 (대금)
용역 대금은 금 {용역 대금} 원(부가세 {부가세 포함 여부})으로 하며, 갑은 {지급일}까지 을에게 지급한다.

제4조 (결과물)
을은 기간 내에 결과물을 갑에게 전달하며, 갑은 전달받은 날부터 7일 이내에 검수한다.

제5조 (특약사항)
{특약사항}

발주자(갑) {발주자 이름} {발주자 서명}
수행자(을) {수행자 이름} {수행자 서명}""",
        "fields": [
            F("발주자 이름"), F("수행자 이름", assignee="B"), F("용역 내용", "LONG_TEXT"), F("시작일", "DATE"), F("종료일", "DATE"),
            F("용역 대금", "NUMBER"), F("부가세 포함 여부", "SELECT", options=["포함", "별도"]), F("지급일", "DATE"),
            F("특약사항", "LONG_TEXT", required=False), F("발주자 서명", "SIGNATURE"), F("수행자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "employment": {
        "id": "employment", "name": "근로계약", "subtitle": "사람을 고용할 때", "contract_type": "employment",
        "title": "표준 근로계약서",
        "body": """사업주 {사업주 이름}(이하 "사업주")과 근로자 {근로자 이름}(이하 "근로자")은 다음과 같이 근로계약을 체결한다.

1. 근로 시작일: {근로 시작일}
2. 근무 장소: {근무 장소}
3. 업무 내용: {업무 내용}
4. 소정근로시간: 하루 {하루 근로시간} 시간
5. 근무일: {근무일}
6. 임금: 월(시간)급 {임금} 원, 지급일: 매월 {임금 지급일} 일
7. 연차유급휴가: 근로기준법에서 정하는 바에 따라 부여함
8. 사회보험 적용: {사회보험 적용}
9. 근로계약서 교부: 사업주는 근로계약을 체결함과 동시에 본 계약서를 근로자에게 교부함
10. 기타: 이 계약에 정함이 없는 사항은 근로기준법령에 의함

근로자 연락처: {근로자 연락처}

사업주 {사업주 이름} {사업주 서명}
근로자 {근로자 이름} {근로자 서명}""",
        "fields": [
            F("사업주 이름"), F("근로자 이름", assignee="B"), F("근로 시작일", "DATE"), F("근무 장소"), F("업무 내용", "LONG_TEXT"),
            F("하루 근로시간", "NUMBER"), F("근무일", "SELECT", options=["주 5일 (월~금)", "주 6일", "기타(특약 참조)"]),
            F("임금", "NUMBER"), F("임금 지급일", "NUMBER"), F("사회보험 적용", "SELECT", options=["4대보험 모두 적용", "일부 적용", "해당 없음"]),
            F("근로자 연락처", "PHONE", assignee="B"), F("사업주 서명", "SIGNATURE"), F("근로자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "goods": {
        "id": "goods", "name": "거래계약", "subtitle": "물건을 사고팔 때", "contract_type": "goods",
        "title": "물품거래계약서",
        "body": """매도인 {매도인 이름}(이하 "갑")과 매수인 {매수인 이름}(이하 "을")은 다음 물품의 거래에 관하여 계약을 체결한다.

제1조 (물품)
품명: {품명}
수량: {수량} 개
단가: {단가} 원

제2조 (대금)
총 거래대금은 금 {총 거래대금} 원으로 하며, 을은 {대금 지급일}까지 갑에게 지급한다.

제3조 (인도)
갑은 {인도일}까지 {인도 장소}에서 을에게 물품을 인도한다.

제4조 (하자)
인도받은 물품에 하자가 있는 경우 을은 인도일부터 7일 이내에 교환 또는 환불을 요구할 수 있다.

제5조 (특약사항)
{특약사항}

매도인(갑) {매도인 이름} {매도인 서명}
매수인(을) {매수인 이름} {매수인 서명}
매수인 이메일: {매수인 이메일}""",
        "fields": [
            F("매도인 이름"), F("매수인 이름", assignee="B"), F("품명"), F("수량", "NUMBER"), F("단가", "NUMBER"),
            F("총 거래대금", "NUMBER"), F("대금 지급일", "DATE"), F("인도일", "DATE"), F("인도 장소"),
            F("특약사항", "LONG_TEXT", required=False), F("매도인 서명", "SIGNATURE"), F("매수인 서명", "SIGNATURE", assignee="B"),
            F("매수인 이메일", "EMAIL", assignee="B", required=False),
        ],
    },
}

CONTRACT_TYPES = {"general": "일반", "loan": "금전소비대차", "service": "용역", "employment": "근로", "goods": "물품거래"}


def list_templates() -> list[dict]:
    return [{"id": t["id"], "name": t["name"], "subtitle": t["subtitle"], "title": t["title"]} for t in TEMPLATES.values()]


def get_template(tid: str) -> dict:
    t = TEMPLATES[tid]
    return {**t, "fields": [FieldSpec(**f).model_dump() for f in t["fields"]]}
