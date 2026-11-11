import { test, expect } from './fixtures.ts'
import { addEntry, createCampaign, entryList, openCampaign, savedWorkspace, section } from './actions.ts'

test('rejects an invalid ZIP without publishing a workspace', async ({ page, server, request }) => {
  await page.goto('/')
  const form = page.locator('form').filter({ has: page.getByRole('button', { name: 'Import campaign', exact: true }) })
  await form.getByLabel('Campaign name', { exact: true }).fill('Invalid campaign')
  await form.getByLabel('Choose a campaign bundle ZIP', { exact: true }).setInputFiles({ name: 'invalid.zip', mimeType: 'application/zip', buffer: Buffer.from('not a ZIP') })
  await form.getByRole('button', { name: 'Import campaign', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(/zip/i)
  expect(await request.get(`${server.url}/api/workspaces`).then(response => response.json())).toEqual([])
})

test('preserves a draft when a stale save conflicts with another edit', async ({ page, server, request }) => {
  await createCampaign(page)
  await addEntry(page, 'Runa', 'The original note.')
  await entryList(page).getByRole('button', { name: /^Runa/ }).click()
  await page.getByRole('button', { name: 'Edit entry', exact: true }).click()
  await page.getByLabel('Description and notes', { exact: true }).fill('My unsaved correction.')
  const original = await savedWorkspace(request, server.url)
  const entry = original.entries[0]!
  const updated = await request.put(`${server.url}/api/workspaces/${original.id}/entries/${entry.concept}`, {
    data: { title: entry.title, type: entry.type, aliases: entry.aliases, related: entry.related, body: 'A newer accepted correction.', base_revision: original.revision },
  })
  expect(updated.ok()).toBeTruthy()
  await page.getByRole('button', { name: 'Save entry', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Campaign changed since this draft was opened.' })).toBeVisible()
  await expect(page.getByLabel('Description and notes', { exact: true })).toHaveValue('My unsaved correction.')
  expect((await savedWorkspace(request, server.url)).entries[0]?.body).toBe('A newer accepted correction.')
})

test('saves a source while AI remains unavailable', async ({ page, server, request }) => {
  await createCampaign(page)
  await section(page, 'Sources').click()
  await page.getByLabel('Source title', { exact: true }).fill('Session notes')
  await page.getByLabel('Session date', { exact: true }).fill('2026-11-03')
  await page.getByLabel('Source text', { exact: true }).fill('Runa opened the lighthouse.')
  await page.getByRole('button', { name: 'Save source', exact: true }).click()
  await expect(page.getByText('AI is not configured on this computer. Manual campaign editing still works.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Review this source with AI', exact: true })).toBeDisabled()
  expect((await savedWorkspace(request, server.url)).sources[0]).toMatchObject({ title: 'Session notes', text: 'Runa opened the lighthouse.' })
})

test.describe('failed extraction', () => {
  test.use({ scenario: 'failed' })
  test('explains the failure and leaves accepted knowledge readable', async ({ page, server, request }) => {
    await openCampaign(page)
    const before = await savedWorkspace(request, server.url, server.seedId)
    await section(page, 'Sources').click()
    await expect(page.getByRole('alert')).toContainText('Your accepted knowledge is unchanged.')
    await expect(page.getByRole('button', { name: 'Retry processing', exact: true })).toBeDisabled()
    await section(page, 'Knowledge').click()
    await entryList(page).getByRole('button', { name: /^Mara/ }).click()
    await expect(page.getByText('GM ruling: Mara owns the inn.', { exact: true })).toBeVisible()
    expect((await savedWorkspace(request, server.url, server.seedId)).entries).toEqual(before.entries)
  })
})
