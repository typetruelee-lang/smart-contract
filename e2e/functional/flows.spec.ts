import { expect, test } from "@playwright/test";
import path from "node:path";
import {
  completeContract, createTextContract, csrf, download, expiredJwt, fillFields, invite, login, newParty,
  runWorkers, setFault, sha256, signFlow,
} from "../fixtures/helpers";

const SAMPLES = path.resolve(__dirname, "../../samples");

test("시나리오 1: 로그인 → 텍스트 계약 → 빈칸 → 입력 → 서명 → 완료 → PDF", async ({ browser }) => {
  const { A, B, id } = await completeContract(browser);
  const pdf = await download(A.page, "dl-contract");
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  // 서버에 기록된 Hash 와 내려받은 파일의 Hash 가 같다
  const view = await (await A.page.request.get(`/api/contracts/${id}`)).json();
  expect(sha256(pdf)).toBe(view.document_hash);
  const cert = await download(A.page, "dl-certificate");
  expect(cert.subarray(0, 5).toString()).toBe("%PDF-");
  // 상대방도 같은 파일을 받는다
  await B.page.goto(`/contracts/${id}/done`);
  expect(sha256(await download(B.page, "dl-contract"))).toBe(view.document_hash);
});

test("시나리오 4·5: 원본 PDF 검증 성공 / 수정본 검증 실패", async ({ browser }) => {
  const { A, id } = await completeContract(browser);
  const pdf = await download(A.page, "dl-contract");
  const vid = (await (await A.page.request.get(`/api/contracts/${id}`)).json()).verification_id;
  const V = await newParty(browser); // 로그인하지 않은 제3자
  await V.page.goto(`/verify/${vid}`);
  await expect(V.page.getByTestId("verify-info")).toContainText(vid);
  await V.page.getByTestId("verify-file").setInputFiles({ name: "계약서.pdf", mimeType: "application/pdf", buffer: pdf });
  await expect(V.page.getByTestId("verify-success")).toContainText("검증 성공");
  const tampered = Buffer.from(pdf);
  tampered[Math.floor(tampered.length / 2)] ^= 0x01;
  await V.page.getByTestId("verify-file").setInputFiles({ name: "수정본.pdf", mimeType: "application/pdf", buffer: tampered });
  await expect(V.page.getByTestId("verify-failed")).toContainText("검증 실패");
  await expect(V.page.getByTestId("verify-failed")).toContainText("다릅니다");
  // 검증번호 없이 PDF 만 올려도 찾을 수 있다
  await V.page.goto("/verify");
  await V.page.getByTestId("verify-file").setInputFiles({ name: "계약서.pdf", mimeType: "application/pdf", buffer: pdf });
  await expect(V.page.getByTestId("verify-success")).toContainText(vid);
  // 공개 페이지에 개인정보가 없다
  await expect(V.page.locator("body")).not.toContainText("홍길동");
  await expect(V.page.locator("body")).not.toContainText("김철수");
});

test("시나리오 3: 결제 → 블록체인(Mock) 기록 → TX → 확인서 반영", async ({ browser }) => {
  const { A, id } = await completeContract(browser);
  await A.page.getByTestId("anchor-buy").click();
  await A.page.getByTestId("pay-success").click();
  await expect(A.page.getByTestId("anchor-status")).toContainText("기록 완료");
  await expect(A.page.getByTestId("anchor-status")).toContainText("0x");
  const st = await (await A.page.request.get(`/api/contracts/${id}/anchor`)).json();
  expect(st.anchor.status).toBe("CONFIRMED");
  expect(st.payment.status).toBe("PAID");
  const cert = await download(A.page, "dl-certificate");
  expect(cert.length).toBeGreaterThan(10_000);
});

test("시나리오 7: 결제 실패 → 블록체인 호출 안 됨", async ({ browser }) => {
  const { A, id } = await completeContract(browser);
  await A.page.getByTestId("anchor-buy").click();
  await A.page.getByTestId("pay-fail").click();
  await expect(A.page.getByTestId("payment-failed")).toBeVisible();
  const st = await (await A.page.request.get(`/api/contracts/${id}/anchor`)).json();
  expect(st.anchor.status).toBe("NOT_REQUESTED");
  expect(st.payment.status).toBe("FAILED");
  const ev = await (await A.page.request.get(`/api/contracts/${id}/events`)).json();
  expect(ev.events.map((e: { event_type: string }) => e.event_type)).not.toContain("BLOCKCHAIN_SUBMITTED");
  // 다시 결제하면 기록된다
  await A.page.getByTestId("anchor-buy").click();
  await A.page.getByTestId("pay-success").click();
  await expect(A.page.getByTestId("anchor-status")).toContainText("기록 완료");
});

test("시나리오 8: 블록체인 실패 → 대기(재시도) → 재시도 → 성공", async ({ browser }) => {
  const { A, id } = await completeContract(browser);
  await setFault(A.page, "blockchain_fail", 2);
  await A.page.getByTestId("anchor-buy").click();
  await A.page.getByTestId("pay-success").click();
  await expect(A.page.getByTestId("anchor-status")).toContainText("다시 시도 중");
  await expect(A.page.getByTestId("anchor-status")).toContainText("결제 완료");
  await A.page.getByTestId("anchor-retry").click(); // 두 번째 실패
  await expect(A.page.getByTestId("anchor-status")).toContainText("시도 2회");
  await runWorkers(A.page); // 세 번째 → 성공
  await A.page.reload();
  await expect(A.page.getByTestId("anchor-status")).toContainText("기록 완료");
  const st = await (await A.page.request.get(`/api/contracts/${id}/anchor`)).json();
  expect(st.anchor.attempts).toBe(3);
});

test("시나리오 2: PDF 업로드 → 텍스트 추출 → 빈칸 → 값 입력 → PDF 생성", async ({ browser }) => {
  const A = await newParty(browser);
  const B = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/create");
  await A.page.getByTestId("create-pdf").click();
  await A.page.getByTestId("pdf-input").setInputFiles(path.join(SAMPLES, "sample-text-contract.pdf"));
  await expect(A.page.getByTestId("pdf-title")).toHaveValue("용역계약서");
  await A.page.getByTestId("apply-pos-all").click();
  await expect(A.page.getByTestId("box-발주자")).toBeVisible();
  // 서명 칸을 직접 추가: 빈칸 추가 → PDF 에서 드래그
  await A.page.getByTestId("add-field-mode").click();
  await A.page.getByTestId("pdf-page-1").evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 120));
  const pg = (await A.page.getByTestId("pdf-page-1").boundingBox())!;
  await A.page.mouse.move(pg.x + pg.width * 0.55, pg.y + pg.height * 0.36);
  await A.page.mouse.down();
  await A.page.mouse.move(pg.x + pg.width * 0.85, pg.y + pg.height * 0.41, { steps: 5 });
  await A.page.mouse.up();
  await A.page.getByTestId("field-label").fill("수행자 서명");
  await A.page.getByTestId("type-SIGNATURE").click();
  await A.page.getByTestId("assignee-B").click();
  await A.page.getByTestId("field-save").click();
  await expect(A.page.getByTestId("box-수행자 서명")).toBeVisible();
  // 필드 이동 (드래그)
  const bx = (await A.page.getByTestId("box-수행자 서명").boundingBox())!;
  await A.page.mouse.move(bx.x + bx.width / 2, bx.y + bx.height / 2);
  await A.page.mouse.down();
  await A.page.mouse.move(bx.x + bx.width / 2 - 20, bx.y + bx.height / 2 + 10, { steps: 4 });
  await A.page.mouse.up();
  // 수행자 칸은 상대방이 입력하도록 변경
  await A.page.getByTestId("chip-수행자").click();
  await A.page.getByTestId("assignee-B").click();
  await A.page.getByTestId("field-save").click();
  await A.page.getByTestId("pdf-save").click();
  await A.page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  const id = A.page.url().split("/").pop()!;
  await fillFields(A.page, { 발주자: "주식회사 가나다", "용역 대금": "3300000", 연락처: "010-2222-3333" });
  const p = await invite(A.page);
  await login(B.page, "kim", p);
  await B.page.getByTestId("accept-invite").click();
  await B.page.waitForURL(/\/contracts\//);
  await fillFields(B.page, { 수행자: "김철수" });
  await B.page.getByTestId("save-values").click();
  await expect(B.page.getByTestId("go-sign")).toBeEnabled();
  await signFlow(B.page);
  await A.page.goto(`/contracts/${id}`);
  await expect(A.page.getByTestId("version-changed")).toBeVisible(); // v1 → v2 (상대방 입력)
  await signFlow(A.page);
  await A.page.waitForURL(/\/done$/);
  const pdf = await download(A.page, "dl-contract");
  const view = await (await A.page.request.get(`/api/contracts/${id}`)).json();
  expect(sha256(pdf)).toBe(view.document_hash);
  expect(view.final_version_no).toBe(2);
});

test("스캔 PDF 업로드 시 OCR 로 빈칸을 찾는다", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/create/pdf");
  await A.page.getByTestId("pdf-input").setInputFiles(path.join(SAMPLES, "sample-scanned-contract.pdf"));
  await expect(A.page.getByTestId("ocr-sug-매도인")).toBeVisible();
});

test("가짜 PDF(확장자 위조) 업로드는 거부된다", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/create/pdf");
  await A.page.getByTestId("pdf-input").setInputFiles({ name: "fake.pdf", mimeType: "application/pdf", buffer: Buffer.from("\x89PNG\r\n\x1a\nnot a pdf") });
  await expect(A.page.getByRole("alert")).toContainText("실제 PDF 파일이 아니에요");
});

test("템플릿으로 시작 + 편집/미리보기 전환 + 필수값 검증", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/");
  await A.page.getByTestId("quick-employment").click();
  await A.page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  await A.page.getByTestId("tab-preview").click();
  await expect(A.page.getByTestId("contract-preview")).toContainText("표준근로계약서");
  await A.page.getByTestId("tab-edit").click();
  await fillFields(A.page, { 임금액: "abc" });
  await expect(A.page.getByTestId("input-임금액")).toHaveValue(""); // 숫자 칸은 숫자만 입력됨
  await fillFields(A.page, { 임금액: "2500000", 임금지급일: "10" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByRole("alert").first()).toContainText("저장했어요");
  await A.page.getByTestId("tab-preview").click();
  await expect(A.page.getByTestId("contract-preview")).toContainText("2,500,000");
});

test("일용근로자 표준근로계약서: 안내 표시 + 근로시간 형식 검증", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/create/template");
  await expect(A.page.getByTestId("template-note-employment_daily")).toContainText("3년간 보존");
  await A.page.getByTestId("template-employment_daily").click();
  await A.page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  await fillFields(A.page, { "근로 시작 시각": "9시" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByText("HH:MM").first()).toBeVisible();
  await fillFields(A.page, { "근로 시작 시각": "09:00", "근로 종료 시각": "18:00" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByRole("alert").first()).toContainText("저장했어요");
  await A.page.getByTestId("tab-preview").click();
  await expect(A.page.getByTestId("contract-preview")).toContainText("일용근로자 표준근로계약서");
  await expect(A.page.getByTestId("contract-preview")).toContainText("09:00");
});

test("단시간근로자 표준근로계약서: 요일별 근로시간 형식 + 가산임금률 50% 미만 거부", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  await A.page.goto("/create/template");
  await expect(A.page.getByTestId("template-note-employment_parttime")).toContainText("15시간 미만");
  await A.page.getByTestId("template-employment_parttime").click();
  await A.page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  await expect(A.page.getByTestId("input-월요일 근로시간")).toHaveAttribute("placeholder", "예: 09:00~13:00");
  await fillFields(A.page, { "월요일 근로시간": "9시~13시" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByText("쉬는 날은 '휴무'").first()).toBeVisible();
  await fillFields(A.page, { "월요일 근로시간": "09:00~13:00", "화요일 근로시간": "휴무", "초과근로 가산임금률": "30" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByText("50 이상이어야 해요").first()).toBeVisible();
  await fillFields(A.page, { "초과근로 가산임금률": "50" });
  await A.page.getByTestId("save-values").click();
  await expect(A.page.getByRole("alert").first()).toContainText("저장했어요");
  await A.page.getByTestId("tab-preview").click();
  await expect(A.page.getByTestId("contract-preview")).toContainText("단시간근로자 표준근로계약서");
  await expect(A.page.getByTestId("contract-preview")).toContainText("09:00~13:00");
});

test("내용 변경 시 새 버전 + 기존 서명 무효화 안내", async ({ browser }) => {
  const A = await newParty(browser);
  const B = await newParty(browser);
  await login(A.page, "hong");
  const id = await createTextContract(A.page);
  await fillFields(A.page, { 대여금액: "5000000", 채권자: "홍길동", 채무자: "김철수", 상환일: "2027-01-31", 이자율: "3" });
  const p = await invite(A.page);
  await login(B.page, "kim", p);
  await B.page.getByTestId("accept-invite").click();
  await B.page.waitForURL(/\/contracts\//);
  await signFlow(B.page);
  await A.page.goto(`/contracts/${id}`);
  await fillFields(A.page, { 대여금액: "6000000" });
  await A.page.getByTestId("save-values").click();
  await B.page.goto(`/contracts/${id}`);
  await expect(B.page.getByTestId("version-changed")).toContainText("5000000");
  await expect(B.page.getByText("다시 서명 필요")).toBeVisible();
});

test("세션 만료 → 로그인 화면으로 이동 후 원래 화면 복귀", async ({ browser }) => {
  test.skip(!process.env.E2E_JWT_SECRET, "외부 서버 대상 실행에서는 서버 비밀값을 알 수 없어 건너뜀");
  const A = await newParty(browser);
  await login(A.page, "hong");
  const me = await (await A.page.request.get("/api/auth/me")).json();
  await A.page.goto("/contracts");
  await A.page.context().addCookies([{ name: "kz_session", value: expiredJwt(me.user.id), domain: "localhost", path: "/", httpOnly: true, sameSite: "Lax" }]);
  await A.page.reload();
  await expect(A.page.getByTestId("session-expired")).toBeVisible();
  await A.page.getByTestId("login-hong").click();
  await A.page.waitForURL(/\/contracts$/);
});

test("뒤로가기 · 새로고침 · 없는 화면 · 없는 계약", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  const id = await createTextContract(A.page);
  await A.page.reload(); // 새로고침해도 상태 유지
  await expect(A.page.getByTestId("my-fields")).toBeVisible();
  await A.page.getByRole("button", { name: "뒤로가기" }).click();
  await expect(A.page).toHaveURL(/\/$/);
  await A.page.goBack();
  await expect(A.page).toHaveURL(new RegExp(`/contracts/${id}$`));
  await A.page.goto("/no-such-page");
  await expect(A.page.getByTestId("error-view")).toContainText("찾으시는 화면이 없어요");
  await A.page.goto("/contracts/00000000000000000000000000000000");
  await expect(A.page.getByTestId("error-view")).toContainText("계약을 찾을 수 없어요");
});

test("다른 사람의 계약은 볼 수 없다 · 초대 링크는 1회용", async ({ browser }) => {
  const A = await newParty(browser);
  const B = await newParty(browser);
  const C = await newParty(browser);
  await login(A.page, "hong");
  const id = await createTextContract(A.page);
  await fillFields(A.page, { 대여금액: "1", 채권자: "a", 채무자: "b", 상환일: "2027-01-01", 이자율: "1" });
  const p = await invite(A.page);
  await login(C.page, "lee");
  await C.page.goto(`/contracts/${id}`);
  await expect(C.page.getByTestId("error-view")).toBeVisible();
  await login(B.page, "kim", p);
  await B.page.getByTestId("accept-invite").click();
  await B.page.waitForURL(/\/contracts\//);
  await C.page.goto(p);
  await expect(C.page.getByTestId("error-view")).toContainText("초대 링크가 올바르지 않아요");
});

test("모바일 화면: 가로 스크롤 없음 · 큰 버튼", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  for (const url of ["/", "/create", "/create/text?mode=new", "/verify", "/contracts"]) {
    await A.page.goto(url);
    await A.page.waitForLoadState("networkidle");
    const overflow = await A.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, url).toBeLessThanOrEqual(0);
  }
  await A.page.goto("/");
  const h = (await A.page.getByTestId("home-create").boundingBox())!.height;
  expect(h).toBeGreaterThanOrEqual(48);
});

test("CSRF 토큰 없는 변경 요청은 거부된다", async ({ browser }) => {
  const A = await newParty(browser);
  await login(A.page, "hong");
  const r = await A.page.request.post("/api/contracts", { data: { title: "x", body_text: "y" } });
  expect(r.status()).toBe(403);
  const ok = await A.page.request.post("/api/contracts", { data: { title: "x", body_text: "y" }, headers: { "X-CSRF-Token": await csrf(A.page) } });
  expect(ok.status()).toBe(200);
});

test("관리자 대시보드가 시스템 상태를 보여준다", async ({ browser }) => {
  const A = await newParty(browser);
  await A.page.goto("/admin");
  await expect(A.page.getByTestId("components")).toContainText("Database");
  await expect(A.page.getByTestId("components")).toContainText("PDF Engine");
  await expect(A.page.getByTestId("components")).not.toContainText("✗");
});


test("로그인 후 외부 주소로 이동시키는 링크(오픈 리다이렉트)는 무시된다", async ({ browser }) => {
  const A = await newParty(browser);
  for (const bad of ["//evil.example", "/\\evil.example", "https://evil.example"]) {
    await A.page.context().clearCookies();
    await A.page.goto(`/login?next=${encodeURIComponent(bad)}`);
    await A.page.getByTestId("login-hong").click();
    await A.page.waitForURL((u) => !u.pathname.startsWith("/login"));
    expect(new URL(A.page.url()).host).toMatch(/^localhost/);
  }
});

test("법적 고지: 로그인 동의 · 서비스 역할 · 이자율 경고 · 완료 안내 · 확인서 진위 검증", async ({ browser }) => {
  const P = await newParty(browser);
  await P.page.goto("/login");
  await expect(P.page.getByTestId("login-consent")).toContainText("이용약관");
  await P.page.goto("/terms");
  await expect(P.page.getByText("회사는 이용자 사이 계약의 당사자가 아니며", { exact: false })).toBeVisible();
  await P.page.goto("/privacy");
  await expect(P.page.getByTestId("legal-draft")).toBeVisible();

  const { A, id } = await completeContract(browser);
  await expect(A.page.getByTestId("completion-notice")).toContainText("직접 보관");
  await expect(A.page.getByTestId("anchor-notice")).toContainText("효력");
  const cert = await download(A.page, "dl-certificate");
  const V = await newParty(browser);
  await V.page.goto("/verify");
  await V.page.getByTestId("verify-file").setInputFiles({ name: "확인서.pdf", mimeType: "application/pdf", buffer: cert });
  await expect(V.page.getByTestId("verify-success")).toContainText("확인서");
  await expect(V.page.getByTestId("verify-success")).toContainText("시험용");
  await expect(V.page.getByTestId("verify-notice")).toContainText("유효한지");

  await A.page.goto("/create");
  await expect(A.page.getByTestId("service-role-notice")).toContainText("당사자가 아니며");
  await A.page.goto("/");
  await A.page.getByTestId("quick-loan").click();
  await A.page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  await fillFields(A.page, { 이자율: "25" });
  await expect(A.page.getByTestId("interest-warning")).toBeVisible();
  void id;
});
