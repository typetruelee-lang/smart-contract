"""빈칸(입력 필드) 시스템.

- 필드 타입 9종: TEXT, NUMBER, DATE, PHONE, EMAIL, SELECT, CHECKBOX, LONG_TEXT, SIGNATURE
- 자동 인식은 '추천(suggestion)'만 만든다. 필드를 확정하는 것은 항상 사용자다.
- 텍스트 계약서 본문에서 필드는 `{라벨}` 형태의 자리표시자로 표현된다.
  (본문이 사람이 읽을 수 있는 상태로 유지되고, 다시 편집해도 필드가 깨지지 않는다)
"""
from __future__ import annotations

import re
import secrets
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FieldType = Literal["TEXT", "NUMBER", "DATE", "PHONE", "EMAIL", "SELECT", "CHECKBOX", "LONG_TEXT", "SIGNATURE"]
FIELD_TYPES: tuple[str, ...] = ("TEXT", "NUMBER", "DATE", "PHONE", "EMAIL", "SELECT", "CHECKBOX", "LONG_TEXT", "SIGNATURE")
Assignee = Literal["A", "B", "ANY"]

MAX_LABEL = 40
MAX_VALUE = {"LONG_TEXT": 2000, "TEXT": 200}
LABEL_RE = re.compile(r"^[^{}<>\n\r]{1,40}$")

# 입력 형식(정규식)은 클라이언트가 보낸 값을 그대로 쓰지 않고, 서버가 아는 형식만 허용한다
# (임의 정규식은 ReDoS 위험). 안내 문구도 서버가 정한다.
PHONE_PATTERN = r"^0\d{1,2}-?\d{3,4}-?\d{4}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
_HM = r"([01]\d|2[0-3]):[0-5]\d"
WORK_RANGE_PATTERN = rf"^(휴무|{_HM} ?[~-] ?{_HM})$"   # 요일별 근로시간: 09:00~13:00 또는 휴무
BREAK_RANGE_PATTERN = rf"^(없음|{_HM} ?[~-] ?{_HM})$"  # 요일별 휴게시간: 12:00~12:30 또는 없음
PATTERN_HINTS = {
    PHONE_PATTERN: "전화번호 형식이 올바르지 않아요. (예: 010-1234-5678)",
    EMAIL_PATTERN: "이메일 형식이 올바르지 않아요.",
    TIME_PATTERN: "시각을 24시간제 HH:MM 으로 입력해 주세요. (예: 09:00)",
    WORK_RANGE_PATTERN: "일하는 날은 09:00~13:00 처럼, 쉬는 날은 '휴무'로 입력해 주세요.",
    BREAK_RANGE_PATTERN: "휴게시간은 12:00~12:30 처럼, 없으면 '없음'으로 입력해 주세요.",
}
# 입력칸 안내(placeholder)와 테스트 예시에 쓰는 올바른 값
PATTERN_EXAMPLES = {
    PHONE_PATTERN: "010-1234-5678", EMAIL_PATTERN: "name@example.com", TIME_PATTERN: "09:00",
    WORK_RANGE_PATTERN: "09:00~13:00", BREAK_RANGE_PATTERN: "없음",
}


class Position(BaseModel):
    """PDF 위 위치. 페이지 크기 대비 비율(0~1)로 저장해 해상도와 무관하게 동작."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class FieldSpec(BaseModel):
    field_id: str = Field(default_factory=lambda: "f_" + secrets.token_hex(4), pattern=r"^f_[a-z0-9]{4,16}$")
    label: str
    type: FieldType = "TEXT"
    value: Any = None
    required: bool = True
    assignee: Assignee = "A"
    page: int | None = Field(default=None, ge=1)
    position: Position | None = None
    options: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        v = v.strip()
        if not LABEL_RE.match(v):
            raise ValueError("빈칸 이름은 1~40자이며 { } < > 줄바꿈을 쓸 수 없어요.")
        return v

    @field_validator("options")
    @classmethod
    def _options(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("선택지는 20개까지 가능해요.")
        return [o.strip()[:50] for o in v if o.strip()]

    @field_validator("validation")
    @classmethod
    def _validation(cls, v: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if v.get("pattern") in PATTERN_HINTS:
            out["pattern"] = v["pattern"]
            out["hint"] = PATTERN_HINTS[v["pattern"]]
            out["example"] = PATTERN_EXAMPLES[v["pattern"]]
        for k in ("maxLength", "min", "max"):
            x = v.get(k)
            if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0:
                out[k] = int(x) if k == "maxLength" else x
        if "maxLength" in out:
            out["maxLength"] = max(1, min(out["maxLength"], max(MAX_VALUE.values())))
        return out


class Suggestion(BaseModel):
    suggestion_id: str
    label: str
    type: FieldType
    required: bool = True
    assignee: Assignee = "A"
    match_text: str
    start: int
    end: int
    line: int
    confidence: float
    reason: str
    options: list[str] = Field(default_factory=list)


# ---------------- 타입 추론 ----------------

_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("SIGNATURE", ("서명", "날인", "(인)")),
    ("PHONE", ("전화", "연락처", "휴대폰", "핸드폰")),
    ("EMAIL", ("이메일", "e-mail", "email", "메일")),
    ("DATE", ("일자", "날짜", "상환일", "계약일", "시작일", "종료일", "납품일", "지급일", "생년월일", "기한", "만료일", "입사일")),
    ("LONG_TEXT", ("특약", "비고", "기타", "업무 내용", "업무내용", "용역 내용", "과업", "내용")),
    ("NUMBER", ("금액", "대여금", "원금", "이자율", "이율", "단가", "수량", "보수", "임금", "급여", "대금", "시급", "월급", "계약금", "잔금", "시간")),
]


def infer_type(label: str, trailing: str = "") -> FieldType:
    l = label.lower()
    for t, words in _TYPE_KEYWORDS:
        if any(w in l for w in words):
            return t  # type: ignore[return-value]
    tr = trailing.strip()
    if tr.startswith(("원", "%", "개", "시간", "일", "개월", "만원")):
        return "NUMBER"
    return "TEXT"


def default_validation(t: str) -> dict[str, Any]:
    return {
        "NUMBER": {"min": 0, "max": 1_000_000_000_000},
        "PHONE": {"pattern": PHONE_PATTERN},
        "EMAIL": {"pattern": EMAIL_PATTERN},
        "TEXT": {"maxLength": 200},
        "LONG_TEXT": {"maxLength": 2000},
    }.get(t, {})


# ---------------- 자동 인식 (추천) ----------------

_DATE_BLANK = re.compile(r"_{2,}\s*년\s*_{1,}\s*월\s*_{1,}\s*일")
_CURLY = re.compile(r"\{([^{}\n]{1,40})\}")
_BRACKET = re.compile(r"\[\s{2,}\]")
_UNDERSCORE = re.compile(r"_{3,}")
_CHECKBOX = re.compile(r"[□☐]\s*([^\n□☐]{1,40})")
_SEAL = re.compile(r"\((?:인|서명)\)")
_EMPTY_AFTER_COLON = re.compile(r"^\s*([^:：\n_]{1,20}?)\s*[:：](\s*_*\s*)$")
_EMPTY_DATE = re.compile(r"(\s*_*\s*년\s+_*\s*월\s+_*\s*일)\s*$")


def _label_before(line: str, col: int) -> tuple[str, str]:
    """빈칸 앞의 '라벨:' 을 찾는다. (라벨, 콜론 뒤~빈칸 사이 접두어)"""
    before = line[:col]
    if ":" in before or "：" in before:
        idx = max(before.rfind(":"), before.rfind("："))
        head = before[:idx]
        label = re.split(r"[,.\s]{2,}|\t|\)\s", head.strip())[-1].strip()
        label = re.sub(r"^[\d]+[.)]\s*|^제\s*\d+\s*조\s*", "", label).strip(" -·")
        return label, before[idx + 1 :]
    # '채권자 _____' 처럼 콜론 없이 바로 이어지는 경우
    words = before.strip().split()
    if words and 2 <= len(words[-1]) <= 12 and not words[-1].endswith(("_", "]", "은", "는", "을", "를", "에게", "와", "과")):
        return words[-1].strip("·-"), ""
    return "", ""


def _unique(label: str, used: dict[str, int]) -> str:
    base = label or "빈칸"
    if base not in used:
        used[base] = 1
        return base
    used[base] += 1
    return f"{base} {used[base]}"


def suggest_fields(text: str, existing_labels: set[str] | None = None) -> list[Suggestion]:
    """본문에서 빈칸 후보를 찾아 추천 목록을 만든다. 본문은 수정하지 않는다."""
    used: dict[str, int] = {l: 1 for l in (existing_labels or set())}
    out: list[Suggestion] = []
    offset = 0
    lines = text.split("\n")
    last_label = ""
    sig_count = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        taken: list[tuple[int, int]] = []

        def free(s: int, e: int) -> bool:
            return all(e <= a or s >= b for a, b in taken)

        def add(s: int, e: int, label: str, t: str, conf: float, reason: str, options: list[str] | None = None, *, curly: bool = False) -> None:
            nonlocal sig_count
            taken.append((s, e))
            if curly:
                lab = label
                if lab in used:
                    return  # 이미 필드로 확정된 자리표시자
                used[lab] = 1
            else:
                lab = _unique(label, used)
            assignee: str = "A"
            if t == "SIGNATURE":
                assignee = "A" if sig_count == 0 else "B"
                sig_count += 1
            out.append(
                Suggestion(
                    suggestion_id="s_" + secrets.token_hex(4), label=lab, type=t, assignee=assignee,  # type: ignore[arg-type]
                    match_text=line[s:e], start=offset + s, end=offset + e, line=i + 1,
                    confidence=conf, reason=reason, options=options or [],
                )
            )

        stripped = line.strip()
        # 밑줄만 있는 줄이 연속되면 하나의 긴 글 입력으로 합친다 (예: 특약사항 아래 빈 줄들)
        if stripped and set(stripped) <= {"_", " "} and len(stripped.replace(" ", "")) >= 3:
            j = i
            end_off = offset + len(line)
            def is_blank_line(k: int) -> bool:
                s2 = lines[k].strip()
                return bool(s2) and set(s2) <= {"_", " "}

            while True:
                k = j + 1
                gap = 0
                while k < len(lines) and not lines[k].strip() and gap < 1:
                    k += 1
                    gap += 1
                if k < len(lines) and is_blank_line(k):
                    for kk in range(j + 1, k + 1):
                        end_off += 1 + len(lines[kk])
                    j = k
                else:
                    break
            label = last_label or "추가 내용"
            lab = _unique(label, used)
            start = offset + line.index(stripped[0])
            out.append(
                Suggestion(
                    suggestion_id="s_" + secrets.token_hex(4), label=lab, type="LONG_TEXT", required=False,
                    match_text=text[start:end_off], start=start, end=end_off, line=i + 1,
                    confidence=0.7, reason="밑줄로 된 줄이 이어져 있어 긴 글 입력으로 추천했어요.",
                )
            )
            for k in range(i, j + 1):
                offset += len(lines[k]) + 1
            i = j + 1
            continue

        for m in _DATE_BLANK.finditer(line):
            label, _ = _label_before(line, m.start())
            add(m.start(), m.end(), label or "날짜", "DATE", 0.9, "'__년 __월 __일' 형식이라 날짜로 추천했어요.")
        for m in _CURLY.finditer(line):
            if free(m.start(), m.end()):
                label = m.group(1).strip()
                add(m.start(), m.end(), label, infer_type(label, line[m.end():]), 0.95, "{ } 로 표시된 빈칸이에요.", curly=True)
        for m in _BRACKET.finditer(line):
            if free(m.start(), m.end()):
                label, _ = _label_before(line, m.start())
                add(m.start(), m.end(), label, infer_type(label, line[m.end():]), 0.75 if label else 0.5, "[   ] 로 표시된 빈칸이에요.")
        for m in _UNDERSCORE.finditer(line):
            if free(m.start(), m.end()):
                label, prefix = _label_before(line, m.start())
                t = infer_type(label + " " + prefix, line[m.end():])
                seal = _SEAL.search(line, m.end())
                if seal and seal.start() - m.end() < 4 and t != "SIGNATURE":
                    t = t  # 이름 칸 + (인) → 이름은 TEXT, 도장 자리는 아래에서 SIGNATURE 로
                add(m.start(), m.end(), label, t, 0.8 if label else 0.5, "밑줄(____)로 된 빈칸이에요." + ("" if label else " 이름을 정해 주세요."))
        for m in _SEAL.finditer(line):
            if free(m.start(), m.end()):
                label, _ = _label_before(line, m.start())
                add(m.start(), m.end(), f"{label} 서명".strip() if label else "서명", "SIGNATURE", 0.85, "(인)/(서명) 자리라 서명으로 추천했어요.")
        for m in _CHECKBOX.finditer(line):
            if free(m.start(), m.end()):
                add(m.start(), m.end(), m.group(1).strip()[:40], "CHECKBOX", 0.8, "□ 체크 표시라 체크박스로 추천했어요.")
        # 스캔(OCR) 문서: 밑줄이 인식되지 않아 '라벨:' 뒤가 비어 있는 경우
        m = _EMPTY_AFTER_COLON.match(line)
        nxt = next((ln.strip() for ln in lines[i + 1 :] if ln.strip()), "")
        header_of_blanks = bool(nxt) and set(nxt) <= {"_", " "}
        if m and not taken and not header_of_blanks:
            label = m.group(1).strip()
            g = m.group(2)
            st = m.start(2) + (len(g) - len(g.lstrip()))
            add(st, m.end(2), label, infer_type(label), 0.6, "'라벨:' 뒤가 비어 있어 빈칸으로 추천했어요. (스캔 문서)")
        m = _EMPTY_DATE.search(line)
        if m and free(m.start(1), m.end(1)):
            label, _ = _label_before(line, m.start(1))
            label = label or line[: m.start(1)].strip().rstrip(":： ")[:40]
            add(m.start(1), m.end(1), label or "날짜", "DATE", 0.6, "'년 월 일' 자리가 비어 있어 날짜로 추천했어요.")

        if stripped.endswith((":", "：")):
            last_label = stripped.rstrip(":： ")[:40]
        elif stripped and not (set(stripped) <= {"_", " "}):
            lab, _ = _label_before(line, len(line))
            last_label = lab or last_label
        offset += len(line) + 1
        i += 1

    out.sort(key=lambda s: s.start)
    return out


def apply_suggestions(text: str, suggestions: list[Suggestion]) -> str:
    """선택한 추천의 빈칸 자리를 `{라벨}` 자리표시자로 바꾼다 (뒤에서부터 치환)."""
    for s in sorted(suggestions, key=lambda s: s.start, reverse=True):
        if text[s.start : s.end] != s.match_text:
            raise ValueError(f"본문이 바뀌어 '{s.label}' 추천을 적용할 수 없어요. 다시 분석해 주세요.")
        repl = "{" + s.label + "}"
        if not s.match_text.strip() and s.start > 0 and text[s.start - 1] not in " \n":
            repl = " " + repl
        text = text[: s.start] + repl + text[s.end :]
    return text


def placeholders_in(text: str) -> list[str]:
    return [m.group(1).strip() for m in _CURLY.finditer(text)]


# ---------------- 값 검증 ----------------

class FieldValueError(ValueError):
    def __init__(self, field_id: str, label: str, message: str):
        super().__init__(message)
        self.field_id = field_id
        self.label = label
        self.message = message


def normalize_value(f: FieldSpec, value: Any) -> Any:
    """입력값을 타입에 맞게 검증/정규화. 문제가 있으면 FieldValueError."""
    def err(msg: str) -> FieldValueError:
        return FieldValueError(f.field_id, f.label, f"{f.label}: {msg}")

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    t = f.type
    v = f.validation or default_validation(t)
    if t in ("TEXT", "LONG_TEXT"):
        if not isinstance(value, str):
            raise err("글자로 입력해 주세요.")
        value = value.replace("\r\n", "\n").strip()
        limit = min(int(v.get("maxLength", MAX_VALUE[t])), MAX_VALUE[t])
        if len(value) > limit:
            raise err(f"{limit}자 이하로 입력해 주세요.")
        if t == "TEXT" and "\n" in value:
            raise err("한 줄로 입력해 주세요.")
        if v.get("pattern") and not re.fullmatch(v["pattern"], value):
            raise err(v.get("hint", "형식이 올바르지 않아요."))
        return value
    if t == "NUMBER":
        s = str(value).replace(",", "").strip()
        if not re.fullmatch(r"-?\d+(\.\d{1,4})?", s):
            raise err("숫자만 입력해 주세요.")
        num = float(s)
        if "min" in v and num < v["min"]:
            raise err(f"{v['min']} 이상이어야 해요.")
        if "max" in v and num > v["max"]:
            mx = v["max"]
            raise err(f"{int(mx) if float(mx).is_integer() else mx:,} 이하로 입력해 주세요.")
        return s
    if t == "DATE":
        try:
            d = date.fromisoformat(str(value))
        except ValueError as e:
            raise err("날짜를 YYYY-MM-DD 형식으로 선택해 주세요.") from e
        if not (1900 <= d.year <= 2200):
            raise err("날짜가 올바르지 않아요.")
        return d.isoformat()
    if t == "PHONE":
        s = str(value).strip()
        if not re.fullmatch(v.get("pattern", PHONE_PATTERN), s):
            raise err("전화번호 형식이 올바르지 않아요. (예: 010-1234-5678)")
        return s
    if t == "EMAIL":
        s = str(value).strip()
        if len(s) > 254 or not re.fullmatch(v.get("pattern", EMAIL_PATTERN), s):
            raise err("이메일 형식이 올바르지 않아요.")
        return s
    if t == "SELECT":
        if str(value) not in f.options:
            raise err("선택지 중에서 골라 주세요.")
        return str(value)
    if t == "CHECKBOX":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("true", "1", "on", "yes"):
            return True
        if str(value).lower() in ("false", "0", "off", "no"):
            return False
        raise err("체크 여부가 올바르지 않아요.")
    if t == "SIGNATURE":
        # 서명 값은 서명 단계에서만 채워진다 (signature blob id)
        s = str(value)
        if not re.fullmatch(r"sig:[a-f0-9]{32}", s):
            raise err("서명은 서명 단계에서만 입력할 수 있어요.")
        return s
    raise err("알 수 없는 입력 유형이에요.")


def validate_field_set(fields: list[FieldSpec], source: str) -> None:
    labels = [f.label for f in fields]
    if len(labels) != len(set(labels)):
        raise ValueError("같은 이름의 빈칸이 있어요. 이름을 다르게 정해 주세요.")
    ids = [f.field_id for f in fields]
    if len(ids) != len(set(ids)):
        raise ValueError("빈칸 ID 가 중복되었어요.")
    if len(fields) > 200:
        raise ValueError("빈칸은 200개까지 만들 수 있어요.")
    for f in fields:
        if f.type == "SELECT" and not f.options:
            raise ValueError(f"'{f.label}' 선택 항목에 선택지를 추가해 주세요.")
        if source == "PDF" and (f.position is None or f.page is None):
            raise ValueError(f"'{f.label}' 빈칸의 PDF 위치를 지정해 주세요.")


def missing_required(fields: list[FieldSpec], assignee: str | None = None, include_signature: bool = False) -> list[FieldSpec]:
    out = []
    for f in fields:
        if not f.required:
            continue
        if f.type == "SIGNATURE" and not include_signature:
            continue
        if assignee and f.assignee not in (assignee, "ANY"):
            continue
        if f.value in (None, "") or (f.type == "CHECKBOX" and f.value is not True):
            out.append(f)
    return out


def display_value(f: FieldSpec) -> str:
    """PDF/미리보기 표시용 문자열."""
    v = f.value
    if v in (None, ""):
        return ""
    if f.type == "NUMBER":
        try:
            s = str(v)
            if "." in s:
                i, d = s.split(".", 1)
                return f"{int(i):,}.{d}"
            return f"{int(s):,}"
        except ValueError:
            return str(v)
    if f.type == "DATE":
        y, m, d = str(v).split("-")
        return f"{int(y)}년 {int(m)}월 {int(d)}일"
    if f.type == "CHECKBOX":
        return "☑" if v is True else "☐"
    return str(v)
