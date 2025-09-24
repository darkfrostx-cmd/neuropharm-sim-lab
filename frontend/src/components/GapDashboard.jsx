import { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import './GapDashboard.css'

function parseNodes(text) {
  return text
    .split(/\n|,/)
    .map((token) => token.trim())
    .filter(Boolean)
}

function formatScore(value) {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

function deriveNodes(items) {
  const ordered = []
  const seen = new Set()
  for (const gap of items) {
    if (!seen.has(gap.subject)) {
      ordered.push(gap.subject)
      seen.add(gap.subject)
    }
    if (!seen.has(gap.object)) {
      ordered.push(gap.object)
      seen.add(gap.object)
    }
  }
  return ordered.slice(0, 12)
}

function buildHeatmap(items) {
  const nodes = deriveNodes(items)
  const matrix = nodes.map((row) =>
    nodes.map((column) =>
      items.find((gap) => gap.subject === row && gap.object === column) || null,
    ),
  )
  return { nodes, matrix }
}

function cellStyle(gap) {
  if (!gap) return {}
  const capped = Math.min(1, Math.max(0, gap.impact_score || gap.impact || 0))
  const hue = 200 - capped * 120
  const lightness = 80 - capped * 35
  return { background: `hsl(${hue}, 75%, ${lightness}%)` }
}

export default function GapDashboard({ onAnalyse, status, error, items, suggestions }) {
  const [input, setInput] = useState(suggestions.join(', '))
  const [selectedGap, setSelectedGap] = useState(null)

  useEffect(() => {
    if (items.length > 0) {
      setSelectedGap(items[0])
    } else {
      setSelectedGap(null)
    }
  }, [items])

  const handleSubmit = (event) => {
    event.preventDefault()
    const nodes = parseNodes(input)
    if (!nodes.length) {
      return
    }
    onAnalyse({ focus_nodes: nodes })
  }

  const heatmap = useMemo(() => buildHeatmap(items), [items])

  return (
    <section className="panel" data-testid="gap-dashboard">
      <header>
        <h2>Gap surfacing</h2>
        <p className="panel-subtitle">Identify missing links amongst focus nodes to steer curation.</p>
      </header>
      <form className="form-grid" onSubmit={handleSubmit}>
        <label htmlFor="gap-focus">Focus nodes</label>
        <textarea
          id="gap-focus"
          rows="2"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Node A, Node B"
          data-testid="gap-input"
        />
        <button type="submit" className="primary" disabled={status === 'loading'} data-testid="gap-button">
          {status === 'loading' ? 'Analysing…' : 'Find gaps'}
        </button>
      </form>
      {error && <p className="form-error" role="alert">{error.message}</p>}
      {items.length > 0 && (
        <div className="gap-layout">
          <div className="gap-list-wrapper">
            <h3>Ranked candidates</h3>
            <ul className="gap-list" data-testid="gap-results">
              {items.map((gap) => (
                <li
                  key={`${gap.subject}-${gap.object}`}
                  className={selectedGap && selectedGap.subject === gap.subject && selectedGap.object === gap.object ? 'active' : ''}
                  onClick={() => setSelectedGap(gap)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') setSelectedGap(gap)
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <span className="gap-pair">{gap.subject} → {gap.object}</span>
                  <span className="gap-reason">{gap.reason}</span>
                  <div className="gap-metrics">
                    <span>Impact {formatScore(gap.impact_score || gap.impact)}</span>
                    <span>Embedding {formatScore(gap.embedding_score)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="gap-heatmap-wrapper">
            <h3>Coverage heatmap</h3>
            <div className="heatmap-scroll">
              <table className="gap-heatmap">
                <thead>
                  <tr>
                    <th aria-label="Empty" />
                    {heatmap.nodes.map((node) => (
                      <th key={`col-${node}`}>{node}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {heatmap.matrix.map((row, rowIndex) => (
                    <tr key={heatmap.nodes[rowIndex]}>
                      <th scope="row">{heatmap.nodes[rowIndex]}</th>
                      {row.map((gap, columnIndex) => (
                        <td
                          key={`${rowIndex}-${columnIndex}`}
                          style={cellStyle(gap)}
                          className={gap && selectedGap && gap.subject === selectedGap.subject && gap.object === selectedGap.object ? 'active' : ''}
                          onClick={() => gap && setSelectedGap(gap)}
                        >
                          {gap ? formatScore(gap.impact_score || gap.impact) : ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {selectedGap && (
            <aside className="gap-detail" data-testid="gap-detail">
              <h3>Gap triage</h3>
              <p className="gap-detail__title">
                <strong>{selectedGap.subject}</strong> → <strong>{selectedGap.object}</strong>
              </p>
              <dl className="gap-detail__metrics">
                <div>
                  <dt>Impact score</dt>
                  <dd>{formatScore(selectedGap.impact_score || selectedGap.impact)}</dd>
                </div>
                <div>
                  <dt>Embedding score</dt>
                  <dd>{formatScore(selectedGap.embedding_score)}</dd>
                </div>
                <div>
                  <dt>Context weight</dt>
                  <dd>{formatScore(selectedGap.metadata?.context_weight)}</dd>
                </div>
                <div>
                  <dt>Uncertainty</dt>
                  <dd>{formatScore(selectedGap.metadata?.context_uncertainty)}</dd>
                </div>
              </dl>
              {selectedGap.reason && <p className="gap-detail__reason">{selectedGap.reason}</p>}
              {selectedGap.literature && selectedGap.literature.length > 0 && (
                <div className="gap-detail__literature">
                  <h4>Suggested literature</h4>
                  <ul>
                    {selectedGap.literature.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              {selectedGap.causal && (
                <div className="gap-detail__causal">
                  <h4>Causal summary</h4>
                  <p>{selectedGap.causal.description}</p>
                </div>
              )}
            </aside>
          )}
        </div>
      )}
    </section>
  )
}

GapDashboard.propTypes = {
  onAnalyse: PropTypes.func.isRequired,
  status: PropTypes.string,
  error: PropTypes.instanceOf(Error),
  items: PropTypes.arrayOf(
    PropTypes.shape({
      subject: PropTypes.string.isRequired,
      object: PropTypes.string.isRequired,
      reason: PropTypes.string,
      impact_score: PropTypes.number,
      impact: PropTypes.number,
      embedding_score: PropTypes.number,
      metadata: PropTypes.object,
      literature: PropTypes.arrayOf(PropTypes.string),
      causal: PropTypes.shape({
        description: PropTypes.string,
      }),
    }),
  ),
  suggestions: PropTypes.arrayOf(PropTypes.string),
}

GapDashboard.defaultProps = {
  status: 'idle',
  error: null,
  items: [],
  suggestions: [],
}

