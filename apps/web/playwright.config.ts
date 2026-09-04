import { defineConfig } from "@playwright/test";

/**
 * Smoke flow only (spec Wave 8): Intelligence → Sarah Chen → walk the score-decomposition
 * chain to the raw observation. Requires the API on :8000 with a seeded + weekly-run DB.
 * CI starts both via `webServer` + a pretest seed step.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:3000",
        reuseExistingServer: true,
        timeout: 60_000,
        env: { NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000" },
      },
});
