import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { startServer, stopServer, type TestServer } from './server.ts'

test('isolates concurrent servers, disables inherited provider credentials, and stops both', async ({ request }, testInfo) => {
  const servers: TestServer[] = []
  const interpreter = process.env.PNP_TEST_PYTHON
  process.env.PNP_TEST_PYTHON = testInfo.outputPath('missing-python')
  try {
    await expect(startServer(testInfo.outputPath('cannot-start'))).rejects.toThrow('Prepare services/dashboard/.venv or set PNP_TEST_PYTHON')
  } finally {
    if (interpreter === undefined) delete process.env.PNP_TEST_PYTHON
    else process.env.PNP_TEST_PYTHON = interpreter
  }
  const key = process.env.DEEPSEEK_API_KEY
  process.env.DEEPSEEK_API_KEY = 'fictional-key-that-must-never-be-used'
  try {
    const started = await Promise.allSettled([
      startServer(testInfo.outputPath('server-state')),
      startServer(testInfo.outputPath('server-state')),
    ])
    for (const result of started) if (result.status === 'fulfilled') servers.push(result.value)
    for (const result of started) if (result.status === 'rejected') throw result.reason
    const [first, second] = servers as [TestServer, TestServer]
    expect(first.url).not.toBe(second.url)
    expect(first.root).not.toBe(second.root)
    expect(await request.get(first.url).then(response => response.text())).toBe(await readFile(join(first.root, 'web', 'index.html'), 'utf8'))
    for (const server of servers) {
      const config = await request.get(`${server.url}/api/workspaces/config`).then((response) => response.json())
      expect(config).toMatchObject({ ai_available: false, model: null })
    }
    const created = await request.post(`${first.url}/api/workspaces`, { data: { name: 'Only in the first server' } })
    expect(created.status(), await created.text()).toBe(201)
    const campaign = await created.json() as { id: string }
    expect(JSON.parse(await readFile(join(first.root, 'workspaces', campaign.id, 'workspace.json'), 'utf8')).name).toBe('Only in the first server')
    expect(await request.get(`${second.url}/api/workspaces`).then((response) => response.json())).toEqual([])
  } finally {
    if (key === undefined) delete process.env.DEEPSEEK_API_KEY
    else process.env.DEEPSEEK_API_KEY = key
    await Promise.all(servers.map(stopServer))
    for (const server of servers) {
      await testInfo.attach(`server-${server.pid}.log`, { body: Buffer.from(server.logs.join('')), contentType: 'text/plain' })
      await expect(fetch(`${server.url}/api/workspaces`)).rejects.toThrow()
    }
  }
})
