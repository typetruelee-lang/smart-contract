import { render, screen } from "@testing-library/react";
import { ContractPreview } from "./contract";
import type { Field } from "../lib/types";

const fields: Field[] = [
  { field_id: "f_aaaa", label: "채권자", type: "TEXT", value: "<b>홍길동</b>", required: true, assignee: "A", page: null, position: null, options: [], validation: {} },
  { field_id: "f_bbbb", label: "대여금액", type: "NUMBER", value: "5000000", required: true, assignee: "A", page: null, position: null, options: [], validation: {} },
  { field_id: "f_cccc", label: "채무자", type: "TEXT", value: null, required: true, assignee: "B", page: null, position: null, options: [], validation: {} },
];

describe("ContractPreview", () => {
  it("입력값을 넣어 보여주고 HTML 은 이스케이프한다", () => {
    const { container } = render(<ContractPreview title="차용증" body={"채권자: {채권자}\n금액: {대여금액} 원\n채무자: {채무자}"} fields={fields} />);
    expect(screen.getByText("5,000,000")).toBeInTheDocument();
    expect(screen.getByText("<b>홍길동</b>")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText("채무자", { selector: "span" })).toBeInTheDocument();
  });
});
