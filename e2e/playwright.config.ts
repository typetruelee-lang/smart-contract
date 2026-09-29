import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { randomBytes } from "node:crypto";

// E2E 전용 포트/DB — 개발 서버와 충돌하지 않게 분리
const API_PORT = 8100;
const WEB_PORT = 5180;
const ROOT = path.resolve(__dirname, "..");
// E2E 실행마다 새로 만드는 테스트 전용 비밀값 (세션 만료 테스트에서 만료된 토큰을 만들기 위해 공유)
process.env.E2E_JWT_SECRET ||= randomBytes(32).toString("hex");
const E2E_ENV = [
  `JWT_SECRET=${process.env.E2E_JWT_SECRET}`,
  "APP_ENV=development",
  "DATABASE_URL=postgresql+psycopg://contract:contract@localhost:5432/contract_e2e",
  "RATE_LIMIT_AUTH_PER_MINUTE=10000",
  "RATE_LIMIT_PER_MINUTE=10000",
  "RATE_LIMIT_UPLOAD_PER_MINUTE=10000",
  "RATE_LIMIT_VERIFY_PER_MINUTE=10000",
  "ANCHOR_RETRY_BASE_SECONDS=0",
  `PUBLIC_BASE_URL=http://localhost:${WEB_PORT}`,
  `CORS_ORIGINS=http://localhost:${WEB_PORT}`,
].join(" ");

export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "../test-results/raw/e2e.json" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    ...devices["iPhone 13"],
    browserName: "chromium",
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "functional", testMatch: /functional\/.*\.spec\.ts/ },
    { name: "visual", testMatch: /visual\/.*\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `cd ${ROOT}/backend && env ${E2E_ENV} .venv/bin/alembic upgrade head && env ${E2E_ENV} .venv/bin/uvicorn app.main:app --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `cd ${ROOT}/frontend && VITE_API_PROXY=http://localhost:${API_PORT} npx vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
