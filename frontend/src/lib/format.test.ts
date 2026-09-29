import { displayValue, shortHash, splitBody, won } from "./format";
import { sha256Hex } from "./hash";
import type { Field } from "./types";

const f = (type: Field["type"], value: Field["value"]): Field => ({ field_id: "f_1234", label: "x", type, value, required: true, assignee: "A", page: null, position: null, options: [], validation: {} });

describe("format", () => {
  it("숫자는 천 단위 구분", () => expect(displayValue(f("NUMBER", "10000000"))).toBe("10,000,000"));
  it("날짜는 한국어", () => expect(displayValue(f("DATE", "2027-03-01"))).toBe("2027년 3월 1일"));
  it("체크박스", () => expect(displayValue(f("CHECKBOX", true))).toBe("☑ 예"));
  it("빈 값", () => expect(displayValue(f("TEXT", null))).toBe(""));
  it("짧은 해시", () => expect(shortHash("a".repeat(64))).toBe("AAAAAAAA…AAAAAAAA"));
  it("원", () => expect(won(990)).toBe("990원"));
  it("본문 자리표시자 분리", () => {
    expect(splitBody("금액 {대여금액} 원, {채무자}")).toEqual([{ text: "금액 " }, { label: "대여금액" }, { text: " 원, " }, { label: "채무자" }]);
  });
  it("스크립트 문자열도 텍스트 조각으로만 취급", () => {
    const parts = splitBody("<script>alert(1)</script>{이름}");
    expect(parts[0].text).toBe("<script>alert(1)</script>");
  });
});

describe("hash", () => {
  it("SHA-256 알려진 값", async () => {
    const buf = new TextEncoder().encode("abc").buffer as ArrayBuffer;
    expect(await sha256Hex(buf)).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
