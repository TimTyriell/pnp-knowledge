import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { startServer, stopServer, type Scenario } from './server.ts'

const scenario = process.argv[2] ?? 'review'
if (!['empty', 'review', 'failed'].includes(scenario)) throw new Error('Scenario must be empty, review, or failed.')
const temporary = await mkdtemp(join(tmpdir(), 'pnp-browser-'))
try {
  const server = await startServer(join(temporary, 'server-state'), scenario as Scenario)
  console.log(`Isolated fictional workbench: ${server.url}\nData: ${server.root}\nPress Ctrl+C to stop.`)
  let stopping = false
  const stop = async () => {
    if (stopping) return
    stopping = true
    await stopServer(server)
    await rm(temporary, { recursive: true, force: true })
  }
  process.once('SIGINT', () => { void stop() })
  process.once('SIGTERM', () => { void stop() })
  server.process.once('exit', () => { void stop() })
} catch (error) {
  await rm(temporary, { recursive: true, force: true })
  throw error
}
