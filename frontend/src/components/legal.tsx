// 법적 고지 문구 — 회사의 역할과 책임 범위를 사용자가 쉽게 이해하도록 여러 화면에서 재사용한다.
// 최종 문구는 법률 검토 후 확정한다 (LEGAL_REVIEW_CHECKLIST.md).
import { Link } from "react-router-dom";

export function ServiceRoleNotice() {
  return (
    <div data-testid="service-role-notice" className="mt-6 rounded-2xl bg-grey-50 p-4 text-[13px] leading-5 text-grey-600">
      <p className="mb-1 font-semibold text-grey-700">시작하기 전에 알아 두세요</p>
      <ul className="list-disc space-y-1 pl-4">
        <li>계약하자는 계약서 작성·서명·보관을 돕는 도구예요. 운영사는 계약의 당사자가 아니며, 계약 내용의 적법성·유효성·이행을 보증하지 않아요.</li>
        <li>부동산 등기, 공증이 필요한 계약, 유언처럼 법이 정한 방식이 따로 있는 계약은 전자계약만으로 효력이 인정되지 않을 수 있어요.</li>
        <li>계약 내용이 법에 어긋나면(예: 법정 최고이자율 초과) 그 부분은 효력이 없을 수 있어요. 중요한 계약은 전문가와 상의해 주세요.</li>
      </ul>
    </div>
  );
}

export function CompletionNotice() {
  return (
    <div data-testid="completion-notice" className="mt-6 rounded-2xl bg-grey-50 p-4 text-[13px] leading-5 text-grey-600">
      <p className="mb-1 font-semibold text-grey-700">꼭 확인해 주세요</p>
      <ul className="list-disc space-y-1 pl-4">
        <li>계약서 PDF 는 각자 직접 보관해야 해요. 서비스는 보존 기간이 지나면 원문을 삭제하고, 디지털 지문과 진행 기록만 남겨요.</li>
        <li>분쟁이 생기면 계약서 PDF 와 '전자계약 체결 확인서' 를 함께 제출하는 것을 권장해요. 증거로서의 효력은 법원이 판단해요.</li>
        <li>확인서는 파일이 기록된 것과 같은지와 진행 기록을 확인해 줄 뿐, 계약이 유효하다는 것을 보증하거나 공증하지 않아요.</li>
      </ul>
    </div>
  );
}

export function LegalFooter() {
  return (
    <footer data-testid="legal-footer" className="mt-10 border-t border-grey-100 pt-4 text-[12px] leading-5 text-grey-500">
      <div className="flex gap-3">
        <Link className="underline" to="/terms">이용약관</Link>
        <Link className="underline font-semibold" to="/privacy">개인정보처리방침</Link>
      </div>
      <p className="mt-2">계약하자는 계약서 작성·전자서명 도구이며, 운영사는 이용자 간 계약의 당사자가 아닙니다.</p>
    </footer>
  );
}
