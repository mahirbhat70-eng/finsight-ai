import { expect, test } from "@playwright/test";

/** Happy path (Playbook P5.6): seed state -> company KPIs -> valuation ->
 * WACC drag moves fair value -> copilot citation card -> jump to source.
 * Deterministic against a seeded stack (docker compose up + make seed). */

test("analyst happy path", async ({ page }) => {
  // 1. Workspace lists the seeded company
  await page.goto("/");
  await expect(page.getByText("NovaTech Industries Ltd")).toBeVisible();

  // 2. Company overview shows KPIs
  await page.getByRole("link", { name: "NovaTech Industries Ltd" }).click();
  await expect(page.getByText("Revenue")).toBeVisible();
  await expect(page.getByText(/EBITDA margin/i)).toBeVisible();

  // 3. Valuation studio: fair value renders, dragging WACC moves it
  await page.getByRole("link", { name: "valuation studio" }).click();
  const fairValue = page.getByText("Fair value / share");
  await expect(fairValue).toBeVisible();
  await expect(page.getByText(/Rs \d+\.\d{2}/).first()).toBeVisible();

  const before = await page
    .getByText(/Rs \d+\.\d{2}/)
    .first()
    .textContent();
  const betaSlider = page.locator("input[type=range]").first();
  await betaSlider.fill("1.6"); // higher beta -> higher Ke -> lower fair value
  await page.waitForTimeout(900); // debounce + request
  const after = await page
    .getByText(/Rs \d+\.\d{2}/)
    .first()
    .textContent();
  expect(Number(after?.replace(/[^\d.]/g, ""))).toBeLessThan(
    Number(before?.replace(/[^\d.]/g, "")),
  );

  // 4. Copilot: ask a question, citation card appears, jump to source
  await page.getByRole("link", { name: "copilot", exact: true }).click();
  await page.getByPlaceholder(/Ask a question/i).fill(
    "Why did EBITDA margin decline in FY2023?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("Grounded", { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  });
  const jump = page.getByText("jump to source").first();
  await expect(jump).toBeVisible();
  await jump.click();
  await expect(page.getByText(/Source document — page \d+/)).toBeVisible();
});
