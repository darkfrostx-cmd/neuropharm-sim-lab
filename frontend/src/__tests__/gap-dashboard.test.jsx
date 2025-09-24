import { render, screen, fireEvent, within } from '@testing-library/react'
import GapDashboard from '../components/GapDashboard'

const SAMPLE_ITEMS = [
  {
    subject: 'CHEBI:28790',
    object: 'HGNC:1033',
    reason: 'Embedding model highlighted this relation as a likely gap. Context: human data.',
    impact_score: 0.76,
    embedding_score: 0.62,
    metadata: { context_weight: 0.85, context_uncertainty: 0.4 },
    literature: ['Example paper [W1]'],
  },
  {
    subject: 'CHEBI:18243',
    object: 'UBERON:0001870',
    reason: 'Embedding model highlighted this relation as a likely gap. Context: limbic circuitry.',
    impact_score: 0.64,
    embedding_score: 0.58,
    metadata: { context_weight: 0.7, context_uncertainty: 0.5 },
    literature: [],
  },
]

test('renders heatmap and detail panel for gaps', () => {
  render(
    <GapDashboard
      onAnalyse={() => {}}
      status="idle"
      error={null}
      items={SAMPLE_ITEMS}
      suggestions={['CHEBI:28790', 'HGNC:1033']}
    />,
  )

  expect(screen.getByText(/Ranked candidates/i)).toBeInTheDocument()
  expect(screen.getByText(/Coverage heatmap/i)).toBeInTheDocument()
  expect(screen.getByTestId('gap-detail')).toBeInTheDocument()

  const [secondGap] = screen.getAllByText(/CHEBI:18243/i)
  fireEvent.click(secondGap)
  const detail = screen.getByTestId('gap-detail')
  expect(within(detail).getByText(/UBERON:0001870/)).toBeInTheDocument()
})
