import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

export type Scenario = 'empty' | 'review' | 'failed'
export type TestServer = {
  url: string
  root: string
  pid: number
  seedId?: string
  process: ChildProcess
  logs: string[]
}

const dashboard = fileURLToPath(new URL('../..', import.meta.url))

export function pythonPath(): string {
  return process.env.PNP_TEST_PYTHON ?? resolve(dashboard, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
}

export async function stopServer(server: TestServer): Promise<void> {
  if (server.process.exitCode !== null || server.process.signalCode !== null) return
  const exited = once(server.process, 'exit')
  server.process.kill('SIGTERM')
  const force = setTimeout(() => server.process.kill('SIGKILL'), 5000)
  try { await exited } finally { clearTimeout(force) }
}

export async function startServer(root: string, scenario: Scenario = 'empty'): Promise<TestServer> {
  root = resolve(root, randomUUID())
  const child = spawn(pythonPath(), ['-u', fileURLToPath(new URL('./server.py', import.meta.url)), resolve(root), '--scenario', scenario], {
    cwd: dashboard,
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const logs: string[] = []
  let output = ''
  try {
    const server = await new Promise<TestServer>((accept, reject) => {
      const timeout = setTimeout(() => reject(new Error(`Browser test server did not become ready.\n${logs.join('')}`)), 20000)
      const finish = () => clearTimeout(timeout)
      child.once('error', (error) => {
        finish()
        reject(new Error(`Cannot start dashboard Python (${pythonPath()}). Prepare services/dashboard/.venv or set PNP_TEST_PYTHON. ${error.message}`))
      })
      child.once('exit', (code, signal) => {
        finish()
        reject(new Error(`Browser test server exited (${code ?? signal}).\n${logs.join('')}`))
      })
      child.stderr!.on('data', (chunk: Buffer) => logs.push(chunk.toString()))
      child.stdout!.on('data', (chunk: Buffer) => {
        const text = chunk.toString()
        logs.push(text)
        output += text
        let newline: number
        while ((newline = output.indexOf('\n')) >= 0) {
          const line = output.slice(0, newline).trim()
          output = output.slice(newline + 1)
          if (!line.startsWith('{')) continue
          try {
            const ready = JSON.parse(line) as { url: string; root: string; pid: number; seedId?: string }
            if (!ready.url?.startsWith('http://127.0.0.1:')) continue
            finish()
            accept({ ...ready, process: child, logs })
          } catch { /* Server logs can contain non-protocol output. */ }
        }
      })
    })
    const response = await fetch(`${server.url}/api/workspaces/config`, { signal: AbortSignal.timeout(5000) })
    const configuration = await response.json() as { ai_available?: boolean }
    if (!response.ok || configuration.ai_available !== false || child.exitCode !== null || child.signalCode !== null) {
      throw new Error('Browser test server must be alive with AI disabled before tests start.')
    }
    return server
  } catch (error) {
    if (child.pid) await stopServer({ url: '', root, pid: child.pid, process: child, logs })
    throw error
  }
}
