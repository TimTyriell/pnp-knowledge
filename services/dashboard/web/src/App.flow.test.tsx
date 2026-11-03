import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const summary = { id: '1'.repeat(32), name: 'Moonfall', description: '', revision: 'r1', entry_count: 0 }

function makeWorkspace(id: string) {
  return {
    ...summary,
    id,
    entries: [] as { concept: string; title: string; type: string; body: string; aliases: string[]; related: string[]; editable: boolean }[],
    sources: [],
    jobs: [],
    proposals: [],
    history: [{ revision: 'r1', message: 'Campaign created', created_at: '2026-11-04T00:00:00Z' }],
  }
}

describe('campaign authoring flows', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('opens a saved campaign and saves a Location entry', async () => {
    let workspace = makeWorkspace(summary.id)
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/config')) return Response.json({ ai_available: false, model: null, max_source_chars: 120000 })
      if (url === '/api/workspaces') return Response.json([summary])
      if (url === `/api/workspaces/${summary.id}`) return Response.json(workspace)
      if (url === `/api/workspaces/${summary.id}/entries` && init?.method === 'POST') {
        const payload = JSON.parse(String(init.body))
        workspace = {
          ...workspace,
          revision: 'r2',
          entry_count: 1,
          entries: [{ concept: 'locations/moonfall-pier', ...payload, editable: true }],
          history: [...workspace.history, { revision: 'r2', message: `Saved ${payload.title}`, created_at: '2026-11-04T00:01:00Z' }],
        }
        return Response.json(workspace)
      }
      return new Response('Not found', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>)

    await screen.findByRole('button', { name: /Moonfall/ })
    fireEvent.click(screen.getByRole('button', { name: /Moonfall/ }))
    fireEvent.click((await screen.findAllByRole('button', { name: 'Add an entry' }))[0])
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Moonfall Pier' } })
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'Location' } })
    fireEvent.change(screen.getByLabelText('Description and notes'), { target: { value: 'A quiet landing by the old lighthouse.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save entry' }))

    await screen.findByRole('button', { name: /Moonfall Pier/ })
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([url, init]) => String(url) === `/api/workspaces/${summary.id}/entries` && init?.method === 'POST')
      expect(saveCall).toBeDefined()
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ title: 'Moonfall Pier', type: 'Location' })
    })
    expect(workspace.entries[0]).toMatchObject({ title: 'Moonfall Pier', type: 'Location' })
  })

  it('keeps an unsaved entry draft when navigating to Sources and back', async () => {
    const id = '2'.repeat(32)
    const workspace = makeWorkspace(id)
    const campaignSummary = { ...summary, id }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/config')) return Response.json({ ai_available: false, model: null, max_source_chars: 120000 })
      if (url === '/api/workspaces') return Response.json([campaignSummary])
      if (url === `/api/workspaces/${id}`) return Response.json(workspace)
      return new Response('Not found', { status: 404 })
    }))

    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>)

    fireEvent.click(await screen.findByRole('button', { name: /Moonfall/ }))
    fireEvent.click(await screen.findAllByRole('button', { name: 'Add an entry' }).then((buttons) => buttons[0]))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'The Glass Orchard' } })
    fireEvent.change(screen.getByLabelText('Description and notes'), { target: { value: 'A grove hidden behind the northern falls.' } })

    fireEvent.click(screen.getByRole('button', { name: /Sources/ }))
    fireEvent.click(screen.getByRole('button', { name: /Knowledge/ }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Add an entry' })[0])

    expect(screen.getByLabelText('Name')).toHaveValue('The Glass Orchard')
    expect(screen.getByLabelText('Description and notes')).toHaveValue('A grove hidden behind the northern falls.')
  })
})
