// 화면 검수용 캡처 — FINAL_REVIEW/*.png (모바일 390×844)
import { expect, test } from "@playwright/test";
import path from "node:path";
import { createTextContract, fillFields, invite, login, newParty, drawSignature, setFault } from "../fixtures/helpers";

const OUT = path.resolve(__dirname, "../../FINAL_REVIEW");
const SAMPLES = path.resolve(__dirname, "../../samples");
async function shot(page: import("@playwright/test").Page, name: string, full = false) {
  await expect(page.getByRole("alert")).toHaveCount(0, { timeout: 6000 }); // 알림이 사라진 뒤 캡처
  await expect(page.getByRole("status")).toHaveCount(0, { timeout: 10000 }); // 로딩 끝난 뒤
  await page.screenshot({ path: path.join(OUT, name), fullPage: full, animations: "disabled" });
}

test("화면 캡처", async ({ browser }) => {
  test.setTimeout(240_000);
  const A = await newParty(browser);
  const B = await newParty(browser);
  const V = await newParty(browser);

  await A.page.goto("/login");
  await shot(A.page, "00-login.png");
  await login(A.page, "hong");
  await A.page.goto("/");
  await A.page.waitForLoadState("networkidle");
  await shot(A.page, "01-home.png");

  await A.page.goto("/create");
  await shot(A.page, "02-contract-create.png");

  // 텍스트 계약서 + 빈칸 추천
  await A.page.getByTestId("create-new").click();
  await A.page.getByTestId("title-input").fill("금전소비대차계약서");
  await A.page.getByTestId("body-input").fill("금전소비대차계약서\n\n대여금액: __________ 원\n\n채권자: __________\n\n채무자: __________\n\n상환일: ____년 __월 __일\n\n이자율: 연 ____%\n\n특약사항:\n\n________________________\n");
  await A.page.getByTestId("find-blanks").click();
  await expect(A.page.getByTestId("suggestions")).toBeVisible();
  await A.page.getByTestId("suggestions").scrollIntoViewIfNeeded();
  await shot(A.page, "02b-field-suggestions.png");
  await A.page.goto("/");

  // PDF 업로드 + 빈칸 편집기
  await A.page.goto("/create/pdf");
  await shot(A.page, "03-pdf-upload.png");
  await A.page.getByTestId("pdf-input").setInputFiles(path.join(SAMPLES, "sample-text-contract.pdf"));
  await expect(A.page.getByTestId("apply-pos-all")).toBeVisible();
  await A.page.getByTestId("apply-pos-all").click();
  await A.page.getByTestId("box-발주자").click({ position: { x: 4, y: 4 } });
  await A.page.getByTestId("pdf-page-1").evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 140));
  await A.page.waitForTimeout(600);
  await shot(A.page, "04-field-editor.png");

  // 계약 생성 → 미리보기
  const id = await createTextContract(A.page);
  await fillFields(A.page, { 대여금액: "10000000", 채권자: "홍길동", 채무자: "김철수", 상환일: "2027-03-31", 이자율: "5", 특약사항: "매월 말일에 이자를 지급한다." });
  await A.page.getByTestId("save-values").click();
  await A.page.getByTestId("tab-preview").click();
  await expect(A.page.getByTestId("contract-preview")).toContainText("10,000,000");
  await shot(A.page, "05-contract-preview.png");
  await A.page.getByTestId("tab-edit").click();
  const p = await invite(A.page);
  await shot(A.page, "05b-invite.png");

  // 상대방 서명 흐름
  await login(B.page, "kim", p);
  await shot(B.page, "05c-invite-accept.png");
  await B.page.getByTestId("accept-invite").click();
  await B.page.waitForURL(/\/contracts\//);
  await B.page.getByTestId("go-sign").click();
  await shot(B.page, "06a-identity.png");
  await B.page.getByTestId("identity-btn").click();
  await B.page.getByText("계약 최종 확인").waitFor();
  for (const t of ["계약 내용을 확인했습니다.", "본인의 의사로 계약합니다.", "전자서명으로 계약을 체결합니다.", "완성된 계약서 파일은 제가 직접 보관합니다. 서비스는 일정 기간이 지나면 원문을 삭제한다는 것을 알고 있습니다."]) await B.page.getByText(t, { exact: true }).click();
  await B.page.getByTestId("confirm-checks").scrollIntoViewIfNeeded();
  await shot(B.page, "06b-final-confirm.png");
  await B.page.getByTestId("review-btn").click();
  await drawSignature(B.page);
  await shot(B.page, "06-signature.png");
  await B.page.getByTestId("sign-btn").click();
  await expect(B.page.getByTestId("waiting-other")).toBeVisible();

  // 작성자 서명 → 완료
  await A.page.goto(`/contracts/${id}/sign`);
  await A.page.getByTestId("identity-btn").click();
  await A.page.getByText("계약 최종 확인").waitFor();
  for (const t of ["계약 내용을 확인했습니다.", "본인의 의사로 계약합니다.", "전자서명으로 계약을 체결합니다.", "완성된 계약서 파일은 제가 직접 보관합니다. 서비스는 일정 기간이 지나면 원문을 삭제한다는 것을 알고 있습니다."]) await A.page.getByText(t, { exact: true }).click();
  await A.page.getByTestId("review-btn").click();
  await drawSignature(A.page);
  await A.page.getByTestId("sign-btn").click();
  await A.page.waitForURL(/\/done$/);
  await expect(A.page.getByTestId("complete-hero")).toBeVisible();
  await shot(A.page, "07-complete.png", true);

  await A.page.goto(`/contracts/${id}/evidence`);
  await shot(A.page, "08-evidence.png", true);

  // 블록체인 기록 (결제 시트 → 기록 완료)
  await A.page.goto(`/contracts/${id}/done`);
  await A.page.getByTestId("anchor-buy").click();
  await shot(A.page, "09a-payment.png");
  await A.page.getByTestId("pay-success").click();
  await expect(A.page.getByTestId("anchor-status")).toContainText("기록 완료");
  await A.page.getByTestId("anchor-status").scrollIntoViewIfNeeded();
  await shot(A.page, "09-blockchain.png");

  // 블록체인 실패 → 재시도 중 화면 (별도 계약)
  const id2 = await createTextContract(A.page);
  await fillFields(A.page, { 대여금액: "300000", 채권자: "홍길동", 채무자: "이영희", 상환일: "2027-01-31", 이자율: "0" });
  const p2 = await invite(A.page);
  const C = await newParty(browser);
  await login(C.page, "lee", p2);
  await C.page.getByTestId("accept-invite").click();
  await C.page.waitForURL(/\/contracts\//);
  for (const pg of [C.page, A.page]) {
    await pg.goto(`/contracts/${id2}/sign`);
    await pg.getByTestId("identity-btn").click();
    await pg.getByText("계약 최종 확인").waitFor();
    for (const t of ["계약 내용을 확인했습니다.", "본인의 의사로 계약합니다.", "전자서명으로 계약을 체결합니다.", "완성된 계약서 파일은 제가 직접 보관합니다. 서비스는 일정 기간이 지나면 원문을 삭제한다는 것을 알고 있습니다."]) await pg.getByText(t, { exact: true }).click();
    await pg.getByTestId("review-btn").click();
    await drawSignature(pg);
    await pg.getByTestId("sign-btn").click();
  }
  await A.page.waitForURL(/\/done$/);
  await setFault(A.page, "blockchain_fail", 1);
  await A.page.getByTestId("anchor-buy").click();
  await A.page.getByTestId("pay-success").click();
  await expect(A.page.getByTestId("anchor-status")).toContainText("다시 시도 중");
  await A.page.getByTestId("anchor-status").scrollIntoViewIfNeeded();
  await shot(A.page, "09b-blockchain-retry.png");

  // 검증 성공 / 실패
  const view = await (await A.page.request.get(`/api/contracts/${id}`)).json();
  const pdf = Buffer.from(await (await A.page.request.get(`/api/contracts/${id}/pdf/contract`)).body());
  await V.page.goto(`/verify/${view.verification_id}`);
  await V.page.getByTestId("verify-file").setInputFiles({ name: "계약서.pdf", mimeType: "application/pdf", buffer: pdf });
  await expect(V.page.getByTestId("verify-success")).toBeVisible();
  await shot(V.page, "10-verification-success.png", true);
  const bad = Buffer.from(pdf);
  bad[Math.floor(bad.length / 2)] ^= 1;
  await V.page.getByTestId("verify-file").setInputFiles({ name: "수정본.pdf", mimeType: "application/pdf", buffer: bad });
  await expect(V.page.getByTestId("verify-failed")).toBeVisible();
  await shot(V.page, "11-verification-failed.png", true);

  await V.page.goto("/admin");
  await expect(V.page.getByTestId("components")).toBeVisible();
  await shot(V.page, "12-admin-dashboard.png", true);

  await V.page.goto("/does-not-exist");
  await shot(V.page, "13-error.png");
  await A.page.goto("/contracts");
  await shot(A.page, "14-my-contracts.png");
});
