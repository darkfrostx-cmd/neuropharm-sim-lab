import { test, expect } from '@playwright/test';

test('graph navigation exposes knowledge flows', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('Top-down exploration')).toBeVisible();
  await expect(page.getByTestId('graph-container')).toBeVisible();

  const graphCanvas = page.locator('[data-testid="graph-container"] canvas').first();
  await expect(graphCanvas).toBeVisible();

  const flowCard = page.getByTestId('flow-card').filter({ hasText: 'Dopamine' }).first();
  await flowCard.click();

  await expect(page.getByRole('status')).toContainText('Highlighting Ventral Striatum');
});

test('atlas overlay updates when selecting alternative flows', async ({ page }) => {
  await page.goto('/');

  const topDownPanel = page.getByRole('region', { name: 'Top-down exploration flows' });
  const flowCards = topDownPanel.getByTestId('flow-card');
  await expect(flowCards).toHaveCount(2);

  await flowCards.nth(1).click();
  await expect(page.getByRole('status')).toContainText('Highlighting Prefrontal Cortex');

  const atlasCanvas = page.getByTestId('atlas-canvas');
  await expect(atlasCanvas).toHaveAttribute('data-active-region', 'Prefrontal Cortex');
});

test('gap dashboard surfaces uncertainty and suggested literature', async ({ page }) => {
  await page.goto('/');

  const gapCards = page.getByTestId('gap-card');
  await expect(gapCards).toHaveCount(2);

  const firstGapLink = gapCards.first().locator('a').first();
  await expect(firstGapLink).toHaveAttribute('href', /doi.org/);
});
