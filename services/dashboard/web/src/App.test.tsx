import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

const campaign = { id: 'a'.repeat(32), name: 'Moonfall', description: '', revision: 'r1', entry_count: 0 }
const renderApp = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>)
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/config')) return Response.json({ ai_available: false, model: null, max_source_chars: 120000 })
    if (init?.method === 'POST' && url.endsWith('/api/workspaces')) return Response.json({ ...campaign, entries: [], sources: [], jobs: [], proposals: [], history: [] })
    if (url.endsWith('/api/workspaces')) return Response.json([])
    if (url.endsWith(`/${campaign.id}`)) return Response.json({ ...campaign, entries: [], sources: [], jobs: [], proposals: [], history: [] })
    return new Response('', { status: 404 })
  }))
})

describe('campaign workbench startup', () => {
  it('offers campaign creation and bundle import without requiring the technical dashboard', () => {
    renderApp()

    expect(screen.getByRole('heading', { name: /campaign workbench/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create campaign/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/choose a campaign bundle zip/i)).toBeInTheDocument()
  })

  it('creates and opens a campaign from the start screen', async () => {
    renderApp()

    fireEvent.change(await screen.findByLabelText('Campaign name', { selector: '#campaign-name' }), { target: { value: 'Moonfall' } })
    fireEvent.click(screen.getAllByRole('button', { name: /create campaign/i })[0])

    expect(await screen.findByRole('heading', { name: 'Moonfall' })).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/workspaces', expect.objectContaining({ method: 'POST' })))
  })
})
