import { test, expect } from '@playwright/test';

test.describe('Neuropharm Sim Lab UI', () => {
  test('renders graph, filters, flows and gaps', async ({ page }) => {
    await page.goto('/', { waitUntil: 'load' });
    await page.waitForSelector('text=Model filters', { timeout: 10000 });

    const slider = page.getByTestId('time-slider');
    await slider.fill('100');
    await expect(page.getByText('Selected: Chronic')).toBeVisible();

    await page.getByLabel('phasic').click();
    await expect(page.getByLabel('phasic')).not.toBeChecked();

    await expect(page.getByRole('heading', { name: 'Top-down reasoning' })).toBeVisible();
    await expect(page.getByTestId('flow-td-1')).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Bottom-up reasoning' })).toBeVisible();
    await expect(page.getByTestId('flow-bu-1')).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Evidence gaps' })).toBeVisible();
    await expect(page.getByTestId('gap-gap-1')).toBeVisible();
  });
});
