import { type Browser, type BrowserContext, type Page, devices, expect } from "@playwright/test";
import { createHash, createHmac } from "node:crypto";
import fs from "node:fs";

export const LOAN_TEXT = `금전소비대차계약서

대여금액: __________ 원

채권자: __________

채무자: __________

상환일: ____년 __월 __일

이자율: 연 ____%

특약사항:

________________________
`;

export async function newParty(browser: Browser): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext({ ...devices["iPhone 13"], locale: "ko-KR", timezoneId: "Asia/Seoul", acceptDownloads: true, baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5180" });
  const page = await ctx.newPage();
  return { ctx, page };
}

export async function login(page: Page, who: "hong" | "kim" | "lee", next = "/") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByTestId(`login-${who}`).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

export async function csrf(page: Page): Promise<string> {
  const c = (await page.context().cookies()).find((x) => x.name === "kz_csrf");
  return c?.value ?? "";
}

export async function setFault(page: Page, key: "blockchain_fail" | "payment_fail", value: number) {
  const r = await page.request.post("/api/dev/faults", { data: { key, value }, headers: { "X-CSRF-Token": await csrf(page) } });
  expect(r.ok()).toBeTruthy();
}

export async function runWorkers(page: Page) {
  const r = await page.request.post("/api/admin/workers/run", { headers: { "X-CSRF-Token": await csrf(page) } });
  expect(r.ok()).toBeTruthy();
}

/** 텍스트 계약서 작성 → 빈칸 자동 찾기 → 모두 적용 → 저장. 계약 id 반환 */
export async function createTextContract(page: Page, text = LOAN_TEXT, title = "금전소비대차계약서"): Promise<string> {
  await page.goto("/create");
  await page.getByTestId("create-new").click();
  await page.getByTestId("title-input").fill(title);
  await page.getByTestId("body-input").fill(text);
  await page.getByTestId("find-blanks").click();
  await expect(page.getByTestId("suggestions")).toBeVisible();
  await page.getByTestId("apply-all").click();
  await expect(page.getByTestId("chip-대여금액")).toBeVisible();
  await page.getByTestId("save-contract").click();
  await page.waitForURL(/\/contracts\/[a-f0-9]{32}$/);
  return page.url().split("/").pop()!;
}

export async function fillFields(page: Page, values: Record<string, string>) {
  for (const [label, v] of Object.entries(values)) {
    const el = page.getByTestId(`input-${label}`);
    const tag = await el.evaluate((n) => n.tagName);
    if (tag === "SELECT") await el.selectOption(v);
    else await el.fill(v);
  }
}

export async function invite(page: Page): Promise<string> {
  await page.getByTestId("invite-btn").click();
  const url = (await page.getByTestId("invite-url").textContent())!.trim();
  expect(url).toContain("/invite/");
  return new URL(url).pathname;
}

export async function drawSignature(page: Page) {
  const pad = page.getByTestId("signature-pad");
  await pad.scrollIntoViewIfNeeded();
  const box = (await pad.boundingBox())!;
  await page.mouse.move(box.x + 30, box.y + box.height * 0.7);
  await page.mouse.down();
  for (let i = 1; i <= 24; i++) {
    await page.mouse.move(box.x + 30 + i * ((box.width - 60) / 24), box.y + box.height * (0.3 + 0.4 * Math.abs(Math.sin(i / 2))));
  }
  await page.mouse.up();
}

/** 계약 화면에서 서명 흐름 전체 (본인확인 → 최종 확인 → 서명) */
export async function signFlow(page: Page) {
  await page.getByTestId("go-sign").click();
  await page.getByTestId("identity-btn").click();
  await page.getByText("계약 최종 확인").waitFor();
  for (const [id, text] of [["chk-content", "계약 내용을 확인했습니다."], ["chk-will", "본인의 의사로 계약합니다."], ["chk-esign", "전자서명으로 계약을 체결합니다."], ["chk-retention", "완성된 계약서 파일은 제가 직접 보관합니다. 서비스는 일정 기간이 지나면 원문을 삭제한다는 것을 알고 있습니다."]]) {
    await page.getByText(text, { exact: true }).click();
    await expect(page.getByTestId(id)).toBeChecked();
  }
  await page.getByTestId("review-btn").click();
  await drawSignature(page);
  await page.getByTestId("sign-btn").click();
}

/** A(홍길동) 가 만들고 B(김철수) 가 참여해서 둘 다 서명 → 완료 화면. */
export async function completeContract(browser: Browser) {
  const A = await newParty(browser);
  const B = await newParty(browser);
  await login(A.page, "hong");
  const id = await createTextContract(A.page);
  await fillFields(A.page, { 대여금액: "10000000", 채권자: "홍길동", 채무자: "김철수", 상환일: "2027-03-31", 이자율: "5", 특약사항: "매월 말일 이자 지급" });
  const path = await invite(A.page);
  await login(B.page, "kim", path);
  await B.page.getByTestId("accept-invite").click();
  await B.page.waitForURL(/\/contracts\//);
  await signFlow(B.page);
  await expect(B.page.getByTestId("waiting-other")).toBeVisible();
  await A.page.goto(`/contracts/${id}`);
  await signFlow(A.page);
  await A.page.waitForURL(/\/done$/);
  await expect(A.page.getByTestId("complete-hero")).toBeVisible();
  return { A, B, id };
}

export async function download(page: Page, testid: string): Promise<Buffer> {
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByTestId(testid).click()]);
  const p = await dl.path();
  return fs.readFileSync(p!);
}

export const sha256 = (b: Buffer) => createHash("sha256").update(b).digest("hex");

export function expiredJwt(sub: string): string {
  const enc = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const head = enc({ alg: "HS256", typ: "JWT" });
  const body = enc({ sub, iat: now - 7200, exp: now - 3600 });
  const sig = createHmac("sha256", process.env.E2E_JWT_SECRET!).update(`${head}.${body}`).digest("base64url");
  return `${head}.${body}.${sig}`;
}
