"""자주 쓰는 계약 템플릿 6종.

본문에는 `{라벨}` 자리표시자를 쓰고, 각 자리표시자의 입력 유형/담당자를 fields 로 정의한다.
주의: 템플릿 문구는 일반적인 예시이며 법률 자문을 대체하지 않는다 (LEGAL_REVIEW_CHECKLIST.md).
"""
from __future__ import annotations

from app.services.fields import BREAK_RANGE_PATTERN, PATTERN_HINTS, TIME_PATTERN, WORK_RANGE_PATTERN, FieldSpec


def F(label, type="TEXT", assignee="A", required=True, options=None):  # noqa: A002
    return {"label": label, "type": type, "assignee": assignee, "required": required, "options": options or []}


def T(label, required=True):
    """시각 입력 (HH:MM, 24시간제)"""
    return {"label": label, "type": "TEXT", "assignee": "A", "required": required, "options": [],
            "validation": {"pattern": TIME_PATTERN, "hint": PATTERN_HINTS[TIME_PATTERN], "maxLength": 5}}


def R(label, pattern):
    """요일별 근로·휴게시간 (09:00~13:00 / 휴무 / 없음)"""
    return {"label": label, "type": "TEXT", "assignee": "A", "required": True, "options": [],
            "validation": {"pattern": pattern, "hint": PATTERN_HINTS[pattern], "maxLength": 13}}


WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


TEMPLATES: dict[str, dict] = {
    "loan": {
        "id": "loan", "group": "everyday", "name": "차용증", "subtitle": "돈을 빌리고 빌려줄 때", "contract_type": "loan",
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
        "id": "service", "group": "everyday", "name": "용역계약", "subtitle": "일을 맡기고 맡을 때", "contract_type": "service",
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
        "id": "employment", "group": "employment", "name": "표준근로계약서", "subtitle": "정규직 등 기간의 정함이 없는 근로자", "contract_type": "employment",
        "title": "표준근로계약서 (기간의 정함이 없는 경우)",
        "body": """{사업체명}(이하 "사업주"라 함)과(와) {근로자 성명}(이하 "근로자"라 함)은 다음과 같이 근로계약을 체결한다.

1. 근로개시일: {근로개시일}부터
2. 근무장소: {근무장소}
3. 업무의 내용: {업무의 내용}
4. 소정근로시간: {근로 시작 시각}부터 {근로 종료 시각}까지 (휴게시간: {휴게 시작 시각} ~ {휴게 종료 시각})
5. 근무일/휴일: 매주 {주 근무일수}일 근무, 주휴일 매주 {주휴일}
6. 임금
 - 임금 형태 및 금액: {임금 형태} {임금액} 원
 - 상여금: {상여금 여부} {상여금액} 원
 - 기타급여(제수당 등): {기타급여}
 - 임금지급일: 매월(매주 또는 매일) {임금지급일} (휴일의 경우는 전일 지급)
 - 지급방법: {지급방법}
7. 연차유급휴가
 - 연차유급휴가는 근로기준법에서 정하는 바에 따라 부여함
8. 사회보험 적용여부
 {고용보험} 고용보험  {산재보험} 산재보험  {국민연금} 국민연금  {건강보험} 건강보험
9. 근로계약서 교부
 - 사업주는 근로계약을 체결함과 동시에 본 계약서를 사본하여 근로자의 교부요구와 관계없이 근로자에게 교부함(근로기준법 제17조 이행). 본 계약서는 전자문서로 교부하며, 근로자는 언제든지 내려받아 출력할 수 있다.
10. 근로계약, 취업규칙 등의 성실한 이행의무
 - 사업주와 근로자는 각자가 근로계약, 취업규칙, 단체협약을 지키고 성실하게 이행하여야 함
11. 기타
 - 이 계약에 정함이 없는 사항은 근로기준법령에 의함
{특약사항}

(사업주) 사업체명: {사업체명} (전화: {사업체 전화})
주소: {사업체 주소}
대표자: {대표자 성명} {사업주 서명}

(근로자) 주소: {근로자 주소}
연락처: {근로자 연락처}
성명: {근로자 성명} {근로자 서명}""",
        "fields": [
            F("사업체명"), F("사업체 전화", "PHONE"), F("사업체 주소"), F("대표자 성명"),
            F("근로개시일", "DATE"), F("근무장소"), F("업무의 내용", "LONG_TEXT"),
            T("근로 시작 시각"), T("근로 종료 시각"), T("휴게 시작 시각"), T("휴게 종료 시각"),
            F("주 근무일수", "NUMBER"), F("주휴일", "SELECT", options=WEEKDAYS),
            F("임금 형태", "SELECT", options=["월급", "일급", "시간급"]), F("임금액", "NUMBER"),
            F("상여금 여부", "SELECT", options=["있음", "없음"]), F("상여금액", "NUMBER", required=False),
            F("기타급여", "LONG_TEXT", required=False), F("임금지급일", "TEXT"),
            F("지급방법", "SELECT", options=["근로자에게 직접지급", "근로자 명의 예금통장에 입금"]),
            F("고용보험", "CHECKBOX", required=False), F("산재보험", "CHECKBOX", required=False),
            F("국민연금", "CHECKBOX", required=False), F("건강보험", "CHECKBOX", required=False),
            F("특약사항", "LONG_TEXT", required=False),
            F("근로자 성명", assignee="B"), F("근로자 주소", assignee="B"), F("근로자 연락처", "PHONE", assignee="B"),
            F("사업주 서명", "SIGNATURE"), F("근로자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "employment_daily": {
        "id": "employment_daily", "group": "employment", "name": "일용근로자 표준근로계약서", "subtitle": "하루·단기로 일하는 근로자", "contract_type": "employment",
        "title": "일용근로자 표준근로계약서",
        "body": """{사업체명}(이하 "사업주"라 함)과(와) {근로자 성명}(이하 "근로자"라 함)은 다음과 같이 근로계약을 체결한다.

1. 근로계약기간: {근로 시작일}부터 {근로 종료일}까지
2. 근무장소: {근무장소}
3. 업무의 내용: {업무의 내용}
4. 소정근로시간: {근로 시작 시각}부터 {근로 종료 시각}까지 (휴게시간: {휴게 시작 시각} ~ {휴게 종료 시각})
5. 근무일/휴일: 매주 {주 근무일수}일(또는 매일단위) 근무, 주휴일 매주 {주휴일} (해당자에 한함)
 ※ 주휴일은 1주간 소정근로일을 모두 근로한 경우에 주당 1일을 유급으로 부여
6. 임금
 - 임금 형태 및 금액: {임금 형태} {임금액} 원
 - 상여금: {상여금 여부} {상여금액} 원
 - 기타 제수당(시간외·야간·휴일근로수당 등): {제수당 내역}
 - 임금지급일: 매월(매주 또는 매일) {임금지급일} (휴일의 경우는 전일 지급)
 - 지급방법: {지급방법}
7. 연차유급휴가
 - 연차유급휴가는 근로기준법에서 정하는 바에 따라 부여함
8. 사회보험 적용여부
 {고용보험} 고용보험  {산재보험} 산재보험  {국민연금} 국민연금  {건강보험} 건강보험
9. 근로계약서 교부
 - 사업주는 근로계약을 체결함과 동시에 본 계약서를 사본하여 근로자의 교부요구와 관계없이 근로자에게 교부함(근로기준법 제17조 이행). 본 계약서는 전자문서로 교부하며, 근로자는 언제든지 내려받아 출력할 수 있다.
10. 근로계약, 취업규칙 등의 성실한 이행의무
 - 사업주와 근로자는 각자가 근로계약, 취업규칙, 단체협약을 지키고 성실하게 이행하여야 함
11. 기타
 - 이 계약에 정함이 없는 사항은 근로기준법령에 의함
{특약사항}

(사업주) 사업체명: {사업체명} (전화: {사업체 전화})
주소: {사업체 주소}
대표자: {대표자 성명} {사업주 서명}

(근로자) 주소: {근로자 주소}
연락처: {근로자 연락처}
성명: {근로자 성명} {근로자 서명}""",
        "fields": [
            F("사업체명"), F("사업체 전화", "PHONE"), F("사업체 주소"), F("대표자 성명"),
            F("근로 시작일", "DATE"), F("근로 종료일", "DATE"), F("근무장소"), F("업무의 내용", "LONG_TEXT"),
            T("근로 시작 시각"), T("근로 종료 시각"), T("휴게 시작 시각"), T("휴게 종료 시각"),
            F("주 근무일수", "NUMBER"), F("주휴일", "SELECT", options=WEEKDAYS + ["해당 없음"]),
            F("임금 형태", "SELECT", options=["일급", "시간급", "월급"]), F("임금액", "NUMBER"),
            F("상여금 여부", "SELECT", options=["있음", "없음"]), F("상여금액", "NUMBER", required=False),
            F("제수당 내역", "LONG_TEXT", required=False), F("임금지급일", "TEXT"),
            F("지급방법", "SELECT", options=["근로자에게 직접지급", "근로자 명의 예금통장에 입금"]),
            F("고용보험", "CHECKBOX", required=False), F("산재보험", "CHECKBOX", required=False),
            F("국민연금", "CHECKBOX", required=False), F("건강보험", "CHECKBOX", required=False),
            F("특약사항", "LONG_TEXT", required=False),
            F("근로자 성명", assignee="B"), F("근로자 주소", assignee="B"), F("근로자 연락처", "PHONE", assignee="B"),
            F("사업주 서명", "SIGNATURE"), F("근로자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "employment_parttime": {
        "id": "employment_parttime", "group": "employment", "name": "단시간근로자 표준근로계약서", "subtitle": "아르바이트 등 통상근로자보다 짧게 일하는 근로자", "contract_type": "employment",
        "title": "단시간근로자 표준근로계약서",
        "body": """{사업체명}(이하 "사업주"라 함)과(와) {근로자 성명}(이하 "근로자"라 함)은 다음과 같이 근로계약을 체결한다.

1. 근로개시일: {근로개시일}부터
 ※ 근로계약기간을 정하는 경우 종료일: {근로 종료일}
2. 근무장소: {근무장소}
3. 업무의 내용: {업무의 내용}
4. 근로일 및 근로일별 근로시간
 - 월요일: {월요일 근로시간} (휴게시간: {월요일 휴게시간})
 - 화요일: {화요일 근로시간} (휴게시간: {화요일 휴게시간})
 - 수요일: {수요일 근로시간} (휴게시간: {수요일 휴게시간})
 - 목요일: {목요일 근로시간} (휴게시간: {목요일 휴게시간})
 - 금요일: {금요일 근로시간} (휴게시간: {금요일 휴게시간})
 - 토요일: {토요일 근로시간} (휴게시간: {토요일 휴게시간})
 - 일요일: {일요일 근로시간} (휴게시간: {일요일 휴게시간})
 - 1주 소정근로시간: {1주 소정근로시간}시간
 - 주휴일: 매주 {주휴일}
 ※ 1주 소정근로시간이 15시간 미만이면 주휴일·연차유급휴가가 적용되지 않음(근로기준법 제18조 제3항)
5. 임금
 - 시간(일, 월)급: {임금 형태} {임금액} 원
 - 상여금: {상여금 여부} {상여금액} 원
 - 기타급여(제수당 등): {기타급여}
 - 초과근로에 대한 가산임금률: {초과근로 가산임금률} %
 ※ 단시간근로자와 사용자 사이에 근로하기로 정한 시간을 초과하여 근로하면 법정 근로시간 내라도 통상임금의 100분의 50 이상의 가산임금 지급(기간제 및 단시간근로자 보호 등에 관한 법률 제6조)
 - 임금지급일: 매월(매주 또는 매일) {임금지급일} (휴일의 경우는 전일 지급)
 - 지급방법: {지급방법}
6. 연차유급휴가
 - 통상근로자의 근로시간에 비례하여 연차유급휴가 부여
7. 사회보험 적용여부
 {고용보험} 고용보험  {산재보험} 산재보험  {국민연금} 국민연금  {건강보험} 건강보험
8. 근로계약서 교부
 - 사업주는 근로계약을 체결함과 동시에 본 계약서를 사본하여 근로자의 교부요구와 관계없이 근로자에게 교부함(근로기준법 제17조 이행). 본 계약서는 전자문서로 교부하며, 근로자는 언제든지 내려받아 출력할 수 있다.
9. 근로계약, 취업규칙 등의 성실한 이행의무
 - 사업주와 근로자는 각자가 근로계약, 취업규칙, 단체협약을 지키고 성실하게 이행하여야 함
10. 기타
 - 이 계약에 정함이 없는 사항은 근로기준법령에 의함
{특약사항}

(사업주) 사업체명: {사업체명} (전화: {사업체 전화})
주소: {사업체 주소}
대표자: {대표자 성명} {사업주 서명}

(근로자) 주소: {근로자 주소}
연락처: {근로자 연락처}
성명: {근로자 성명} {근로자 서명}""",
        "fields": [
            F("사업체명"), F("사업체 전화", "PHONE"), F("사업체 주소"), F("대표자 성명"),
            F("근로개시일", "DATE"), F("근로 종료일", "DATE", required=False), F("근무장소"), F("업무의 내용", "LONG_TEXT"),
            *[R(f"{d} {k}", p) for d in WEEKDAYS for k, p in (("근로시간", WORK_RANGE_PATTERN), ("휴게시간", BREAK_RANGE_PATTERN))],
            F("1주 소정근로시간", "NUMBER"), F("주휴일", "SELECT", options=WEEKDAYS + ["해당 없음"]),
            F("임금 형태", "SELECT", options=["시간급", "일급", "월급"]), F("임금액", "NUMBER"),
            F("상여금 여부", "SELECT", options=["있음", "없음"]), F("상여금액", "NUMBER", required=False),
            F("기타급여", "LONG_TEXT", required=False),
            {**F("초과근로 가산임금률", "NUMBER"), "validation": {"min": 50, "max": 1000}},
            F("임금지급일", "TEXT"),
            F("지급방법", "SELECT", options=["근로자에게 직접지급", "근로자 명의 예금통장에 입금"]),
            F("고용보험", "CHECKBOX", required=False), F("산재보험", "CHECKBOX", required=False),
            F("국민연금", "CHECKBOX", required=False), F("건강보험", "CHECKBOX", required=False),
            F("특약사항", "LONG_TEXT", required=False),
            F("근로자 성명", assignee="B"), F("근로자 주소", assignee="B"), F("근로자 연락처", "PHONE", assignee="B"),
            F("사업주 서명", "SIGNATURE"), F("근로자 서명", "SIGNATURE", assignee="B"),
        ],
    },
    "goods": {
        "id": "goods", "group": "everyday", "name": "거래계약", "subtitle": "물건을 사고팔 때", "contract_type": "goods",
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

# 템플릿별 안내 (법정 기재사항 · 보존 의무 등) — 화면과 문서에 표시
TEMPLATE_NOTES = {
    "employment": "고용노동부 표준근로계약서(기간의 정함이 없는 경우) 항목을 따랐어요. 근로기준법 제17조에 따라 임금·근로시간·휴일·연차휴가 등을 반드시 적어야 하고, 계약서를 근로자에게 교부해야 해요. 사업주는 계약서를 3년간 보존해야 해요. 임금은 최저임금 이상이어야 해요. 통상근로자보다 짧게 일하면 '단시간근로자 표준근로계약서'를 쓰고, 기간제 근로자는 별도 양식이 필요할 수 있어요.",
    "employment_parttime": "고용노동부 단시간근로자 표준근로계약서 항목을 따랐어요. 요일마다 근로시간과 휴게시간을 적어야 해요(4시간 일하면 30분 이상 휴게). 약속한 시간을 넘겨 일하면 통상임금의 50% 이상을 더 줘야 하고, 1주 15시간 미만이면 주휴일·연차가 적용되지 않아요. 계약서를 근로자에게 교부하고 사업주는 3년간 보존해야 해요.",
    "employment_daily": "고용노동부 일용근로자 표준근로계약서 항목을 따랐어요. 계약서를 근로자에게 교부해야 하고, 사업주는 3년간 보존해야 해요. 임금은 최저임금 이상이어야 하며, 시간외·야간·휴일근로수당은 법에서 정한 가산율 이상이어야 해요.",
}


# 화면 표시 순서: 누구나 쓰는 일상 계약 → 전문 서식(근로계약서)
GROUPS = {"everyday": "자주 쓰는 계약", "employment": "근로계약서"}


def list_templates() -> list[dict]:
    items = [{"id": t["id"], "group": t["group"], "name": t["name"], "subtitle": t["subtitle"], "title": t["title"],
              "note": TEMPLATE_NOTES.get(t["id"])} for t in TEMPLATES.values()]
    order = list(GROUPS)
    return sorted(items, key=lambda t: order.index(t["group"]))


def get_template(tid: str) -> dict:
    t = TEMPLATES[tid]
    return {**t, "note": TEMPLATE_NOTES.get(tid), "fields": [FieldSpec(**f).model_dump() for f in t["fields"]]}
