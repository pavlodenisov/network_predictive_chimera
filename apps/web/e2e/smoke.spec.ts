import { expect, test } from "@playwright/test";

test("Intelligence → Sarah Chen → evidence chain", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Intelligence" })).toBeVisible();

  // Sarah Chen is present in the ranked table
  const sarah = page.getByRole("link", { name: "Sarah Chen" }).first();
  await expect(sarah).toBeVisible();
  await sarah.click();
  await page.waitForURL(/\/person\//);

  // Person screen: priority, weekly delta, confidence shown separately
  await expect(page.locator("h2", { hasText: "Sarah Chen" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/separate from priority/).first()).toBeVisible();
  await expect(page.getByText(/SCORE DECOMPOSITION/i)).toBeVisible();

  // the timing dimension carries the departure signal
  await expect(page.getByText(/EMPLOYMENT_ENDED/).first()).toBeVisible();

  // unknown fundraising status is shown as the literal word, never 0
  await expect(page.getByText(/"status":"unknown"/).first()).toBeVisible();

  // evidence chain reaches an immutable observation
  await expect(page.getByText(/FACTS TRACE TO AN IMMUTABLE SOURCE RECORD/i)).toBeVisible();
});

test("Models screen shows versioned weights", async ({ page }) => {
  await page.goto("/models");
  await expect(page.getByText("founder_v0.1", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("dimension weights", { exact: false }).first()).toBeVisible();
});

test("Weekly Runs screen lists a run with a digest", async ({ page }) => {
  await page.goto("/weekly-runs");
  await expect(page.getByRole("heading", { name: "Weekly Runs" })).toBeVisible();
  await page.getByRole("button", { name: "audit trail" }).first().click();
  await expect(page.getByText("Stage stats", { exact: false })).toBeVisible();
});
