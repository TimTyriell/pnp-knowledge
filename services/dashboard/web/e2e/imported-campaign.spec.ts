import { execFileSync } from 'node:child_process'
import type { APIRequestContext } from '@playwright/test'
import { test, expect } from './fixtures.ts'
import { entryList, openCampaign } from './actions.ts'
import { pythonPath } from './server.ts'

const document = (type: string, id: string, title: string, folder: string, body: string) => `---
type: ${type}
id: ${id}
title: ${title}
description: ${title} from an imported fictional campaign
tags:
  - ${folder}
timestamp: '2026-11-04T00:00:00Z'
aliases: []
---

${body}
`

const windowsMarkdown = (text: string) => text.replace(/\n/g, '\r\n')

const zipBytes = (files: Record<string, string>) => {
  const script = [
    'import io, json, sys, zipfile',
    'buffer = io.BytesIO()',
    "with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:",
    '    for path, content in json.load(sys.stdin).items():',
    '        archive.writestr(path, content)',
    'sys.stdout.buffer.write(buffer.getvalue())',
  ].join('\n')
  return execFileSync(pythonPath(), ['-c', script], {
    input: JSON.stringify(files),
    maxBuffer: 20 * 1024 * 1024,
  })
}

async function importBundle(request: APIRequestContext, url: string, files: Record<string, string>, name: string) {
  const response = await request.post(`${url}/api/workspaces/import?name=${encodeURIComponent(name)}`, {
    data: zipBytes(files),
    headers: { 'Content-Type': 'application/zip' },
  })
  expect(response.status(), await response.text()).toBe(201)
  return await response.json() as { id: string }
}

test('follows imported Markdown links to entries without leaving Knowledge', async ({ page, request, server }) => {
  const relationships = (target: string) => `relationships:\n  - target: ${target}\n    kind: sibling\n    note: raised together\n`
  const runa = document('NPC', 'NPC_RUNA', 'Runa', 'npcs', 'Runa keeps the lantern. Visit [Copper Lantern](/locations/copper-lantern.md).')
    .replace('aliases: []\n', `aliases: []\ncustom: keep-me\n${relationships('locations/copper-lantern')}`)
  const lantern = document('Location', 'LOC_COPPER_LANTERN', 'Copper Lantern', 'locations', 'The innkeeper is [Runa](../npcs/runa.md).')
    .replace('aliases: []\n', `aliases: []\n${relationships('npcs/runa')}`)
  const imported = await importBundle(request, server.url, {
    'bundle/coast/npcs/runa.md': windowsMarkdown(runa),
    'bundle/coast/locations/copper-lantern.md': windowsMarkdown(lantern),
  }, 'Imported Link Coast')

  await openCampaign(page, 'Imported Link Coast')
  await entryList(page).getByRole('button', { name: /^Runa/ }).click()
  const appUrl = page.url()
  await page.getByRole('link', { name: 'Copper Lantern', exact: true }).click()
  await expect(page).toHaveURL(appUrl)
  await expect(entryList(page).getByRole('button', { name: /^Copper Lantern/ })).toHaveClass(/active/)
  await expect(page.locator('.entry-detail').getByText('Copper Lantern', { exact: true })).toBeVisible()

  await page.locator('.entry-detail').getByRole('link', { name: 'Runa', exact: true }).click()
  await expect(page).toHaveURL(appUrl)
  await expect(entryList(page).getByRole('button', { name: /^Runa/ })).toHaveClass(/active/)

  await page.getByRole('button', { name: 'Edit entry', exact: true }).click()
  await page.getByLabel('Description and notes', { exact: true }).fill('Updated after importing the Windows bundle.')
  await page.getByRole('button', { name: 'Save entry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save entry', exact: true })).toHaveCount(0)

  const exportResponse = await request.get(`${server.url}/api/workspaces/${imported.id}/export`)
  expect(exportResponse.ok()).toBeTruthy()
  const inspect = [
    'import io, json, sys, zipfile, yaml',
    "with zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())) as archive:",
    "    content = archive.read('bundle/coast/npcs/runa.md').decode('utf-8')",
    "    frontmatter = yaml.safe_load(content.split('---', 2)[1])",
    "    print(json.dumps({'frontmatter': frontmatter, 'body': content.split('---', 2)[2]}))",
  ].join('\n')
  const exported = JSON.parse(execFileSync(pythonPath(), ['-c', inspect], {
    input: await exportResponse.body(),
    encoding: 'utf8',
  })) as { frontmatter: Record<string, unknown>; body: string }
  expect(exported.frontmatter.custom).toBe('keep-me')
  expect(exported.frontmatter.relationships).toEqual([{ target: 'locations/copper-lantern', kind: 'sibling', note: 'raised together' }])
  expect(exported.body).toContain('Updated after importing the Windows bundle.')
})

test('shows imported session documents as read-only', async ({ page, request, server }) => {
  await importBundle(request, server.url, {
    'npcs/mara.md': document('NPC', 'NPC_MARA', 'Mara', 'npcs', 'Mara runs the harbor inn.'),
    'sessions/session-one.md': document('Session', '', 'Session One', 'sessions', 'The party reached the old harbor.'),
  }, 'Imported Session Coast')

  await openCampaign(page, 'Imported Session Coast')
  await entryList(page).getByRole('button', { name: /^Session One/ }).click()
  const detail = page.locator('.entry-detail')
  await expect(detail.getByRole('button', { name: 'Edit entry', exact: true })).toHaveCount(0)
  await expect(detail.getByText(/read-only/i)).toBeVisible()
  await expect(detail.getByText('The party reached the old harbor.', { exact: true })).toBeVisible()
})

test('keeps an imported 1,182-entry list bounded and selected details reachable on a narrow screen', async ({ page, request, server }) => {
  const files: Record<string, string> = {}
  const entryCount = 1182
  const types = [
    ['Character', 'characters', 'CHAR'],
    ['NPC', 'npcs', 'NPC'],
    ['Location', 'locations', 'LOC'],
    ['Faction', 'factions', 'FACTION'],
    ['Item', 'items', 'ITEM'],
    ['Event', 'events', 'EVENT'],
    ['Deity', 'deities', 'DEITY'],
    ['Domain', 'domains', 'DOMAIN'],
  ] as const
  for (let index = 0; index < entryCount; index += 1) {
    const token = (index * 2654435761 >>> 0).toString(36)
    const slug = `fixture-${index.toString(36)}-${token}`
    const [type, folder, prefix] = types[index % types.length]!
    files[`${folder}/${slug}.md`] = windowsMarkdown(document(type, `${prefix}_FIXTURE_${index}`, `Fixture Person ${index}`, folder, `Fictional imported entry ${index}.`))
  }
  await importBundle(request, server.url, files, 'Imported Large Coast')

  await page.setViewportSize({ width: 390, height: 844 })
  await openCampaign(page, 'Imported Large Coast')
  const listPanel = entryList(page)
  const list = listPanel.locator('.entry-list-items')
  const dimensions = await list.evaluate(element => ({ scrollHeight: element.scrollHeight, clientHeight: element.clientHeight }))
  expect.soft(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight)

  const lastName = `Fixture Person ${entryCount - 1}`
  await listPanel.getByRole('button', { name: new RegExp(`^${lastName}`) }).click()
  const selectedDetail = page.locator('.entry-detail').getByText(lastName, { exact: true })
  await expect(selectedDetail).toBeVisible()
  await expect.soft(selectedDetail).toBeInViewport()
})
