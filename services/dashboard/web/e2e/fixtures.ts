import { test as base, expect } from '@playwright/test'
import { startServer, stopServer, type Scenario, type TestServer } from './server.ts'

export const test = base.extend<{ scenario: Scenario; server: TestServer }>({
  scenario: ['empty', { option: true }],
  server: async ({ scenario }, provide, testInfo) => {
    const server = await startServer(testInfo.outputPath('server-state'), scenario)
    try { await provide(server) } finally {
      await stopServer(server)
      await testInfo.attach('server.log', { body: Buffer.from(server.logs.join('')), contentType: 'text/plain' })
    }
  },
  baseURL: async ({ server }, provide) => { await provide(server.url) },
  context: async ({ context, server }, provide, testInfo) => {
    const errors: string[] = []
    const pageErrors: string[] = []
    const external: string[] = []
    await context.route('**/*', async (route) => {
      const url = route.request().url()
      if (new URL(url).origin === server.url || /^(data|blob):/.test(url)) {
        await route.continue()
      } else {
        external.push(url)
        await route.abort('blockedbyclient')
      }
    })
    context.on('page', (page) => {
      page.on('pageerror', (error) => {
        pageErrors.push(error.message)
        errors.push(`pageerror: ${error.message}`)
      })
      page.on('console', (message) => {
        if (message.type() === 'error') errors.push(`console: ${message.text()}`)
      })
      page.on('requestfailed', (request) => errors.push(`requestfailed: ${request.url()} ${request.failure()?.errorText}`))
    })
    await provide(context)
    await testInfo.attach('browser.log', { body: Buffer.from(errors.join('\n')), contentType: 'text/plain' })
    expect(pageErrors, 'Unexpected uncaught browser errors').toEqual([])
    expect(external, 'Unexpected external browser requests').toEqual([])
  },
  page: async ({ page }, provide) => {
    await page.clock.setFixedTime(new Date('2026-11-04T12:00:00Z'))
    await provide(page)
  },
})

export { expect }
