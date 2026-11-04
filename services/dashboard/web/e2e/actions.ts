import { expect, type APIRequestContext, type Page } from '@playwright/test'
import type { Workspace } from '../src/workbench.ts'

export const section = (page: Page, name: string) => page.getByRole('navigation', { name: 'Campaign sections' }).getByRole('button', { name: new RegExp(`^${name}`) })
export const entryList = (page: Page) => page.locator('[data-slot="card"]').filter({ has: page.getByText('Campaign knowledge', { exact: true }) })
export const proposal = (page: Page, name: string) => page.locator('[data-slot="card"]').filter({ has: page.getByLabel(`Suggested note for ${name}`, { exact: true }) })

export async function createCampaign(page: Page, name = 'Moonfall') {
  await page.goto('/')
  const form = page.locator('form').filter({ has: page.getByRole('button', { name: 'Create campaign', exact: true }) })
  await form.getByLabel('Campaign name', { exact: true }).fill(name)
  await form.getByRole('button', { name: 'Create campaign', exact: true }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
}

export async function openCampaign(page: Page, name = 'Copper Coast') {
  await page.goto('/')
  await page.getByRole('button', { name: new RegExp(`^${name}`) }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
}

export async function addEntry(page: Page, name: string, body: string, type = 'NPC', related?: string) {
  await entryList(page).getByRole('button', { name: 'Add an entry', exact: true }).click()
  await page.getByLabel('Name', { exact: true }).fill(name)
  await page.getByLabel('Type', { exact: true }).selectOption(type)
  await page.getByLabel('Description and notes', { exact: true }).fill(body)
  if (related) await page.getByRole('checkbox', { name: new RegExp(`^${related}`) }).check()
  await page.getByRole('button', { name: 'Save entry', exact: true }).click()
  await expect(entryList(page).getByRole('button', { name: new RegExp(`^${name}`) })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save entry', exact: true })).toHaveCount(0)
}

export async function savedWorkspace(request: APIRequestContext, url: string, id?: string): Promise<Workspace> {
  if (!id) {
    const listing = await request.get(`${url}/api/workspaces`)
    expect(listing.ok()).toBeTruthy()
    const workspaces = await listing.json() as Workspace[]
    expect(workspaces).toHaveLength(1)
    id = workspaces[0]!.id
  }
  const response = await request.get(`${url}/api/workspaces/${id}`)
  expect(response.ok()).toBeTruthy()
  return await response.json() as Workspace
}
