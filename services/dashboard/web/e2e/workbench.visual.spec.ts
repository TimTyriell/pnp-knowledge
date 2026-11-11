import { test, expect } from './fixtures.ts'
import { entryList, openCampaign, proposal, section } from './actions.ts'

test.use({ scenario: 'review' })

test.beforeEach(() => {
  expect(process.platform, 'Visual comparisons require the canonical Linux Playwright container.').toBe('linux')
})

for (const [size, viewport] of Object.entries({ desktop: { width: 1440, height: 900 }, narrow: { width: 390, height: 844 } })) {
  test(`campaign start ${size}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    await expect(page.getByRole('button', { name: /^Copper Coast/ })).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(`campaign-start-${size}.png`, { fullPage: true })
  })

  test(`populated editor ${size}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await openCampaign(page)
    await entryList(page).getByRole('button', { name: /^Mara/ }).click()
    await page.getByRole('button', { name: 'Edit entry', exact: true }).click()
    await expect(page.getByLabel('Description and notes', { exact: true })).toHaveValue('GM ruling: Mara owns the inn.')
    await expect(page.getByText(/Syncing/)).toHaveCount(0)
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(`knowledge-editor-${size}.png`, { fullPage: true, mask: [page.locator('footer code')] })
  })

  test(`identity review ${size}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await openCampaign(page)
    await section(page, 'Review').click()
    const ambiguous = proposal(page, 'Copper Towr')
    await ambiguous.getByRole('button', { name: 'Accept suggestion', exact: true }).click()
    await expect(ambiguous.getByLabel('Apply this note to', { exact: true })).toHaveValue('')
    await expect(page.getByText(/Syncing/)).toHaveCount(0)
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(`identity-review-${size}.png`, { fullPage: true, mask: [page.locator('footer code')] })
  })
}
