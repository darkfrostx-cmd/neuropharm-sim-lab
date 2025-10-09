import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import ResearchQueue from '../components/ResearchQueue'

afterEach(() => {
  vi.resetAllMocks()
})

test('renders research queue items and submits comment updates', async () => {
  const firstEntry = {
    id: 'HGNC:HTR1A|biolink:positively_regulates|HGNC:BDNF',
    subject: 'HGNC:HTR1A',
    object: 'HGNC:BDNF',
    predicate: 'biolink:positively_regulates',
    status: 'new',
    priority: 3,
    watchers: ['analyst@example.org'],
    created_at: '2024-06-05T10:00:00Z',
    updated_at: '2024-06-05T10:00:00Z',
    metadata: { context: 'Chronic regimen follow-up' },
    comments: [
      {
        author: 'triager@example.org',
        body: 'Initial triage note',
        created_at: '2024-06-05T10:00:00Z',
      },
    ],
    history: [],
  }

  const fetchMock = vi.spyOn(global, 'fetch').mockImplementation((url, options) => {
    if (options && options.method === 'PATCH') {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ...firstEntry,
          status: 'triaging',
          watchers: [...firstEntry.watchers, 'observer@example.org'],
          comments: [
            ...firstEntry.comments,
            {
              author: 'curator@example.org',
              body: 'Replicating experiment',
              created_at: '2024-06-05T12:00:00Z',
            },
          ],
          updated_at: '2024-06-05T12:00:00Z',
        }),
      })
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ items: [firstEntry] }),
    })
  })

  render(<ResearchQueue apiBaseUrl="http://localhost:8000" currentUser="curator@example.org" />)

  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  expect(screen.getByText(/Research Queue/i)).toBeInTheDocument()
  expect(screen.getAllByText(/HGNC:HTR1A/i).length).toBeGreaterThan(0)

  const textarea = await screen.findByPlaceholderText(/Add a triage note/i)
  fireEvent.change(textarea, { target: { value: 'Replicating experiment' } })
  await waitFor(() => expect(textarea.value).toBe('Replicating experiment'))
  fireEvent.click(screen.getByText(/Comment/i))

  await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3))
  const patchCall = fetchMock.mock.calls.find(([, options]) => options && options.method === 'PATCH')
  expect(patchCall).toBeDefined()
  expect(patchCall?.[0]).toBe('http://localhost:8000/research-queue/HGNC:HTR1A|biolink:positively_regulates|HGNC:BDNF')

  expect(await screen.findByText(/Replicating experiment/i)).toBeInTheDocument()
  expect(screen.getAllByText(/triaging/i).length).toBeGreaterThan(0)
})
