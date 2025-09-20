import { useState } from 'react'
import PropTypes from 'prop-types'
import './GapDashboard.css'

function parseNodes(text) {
  return text
    .split(/\n|,/)
    .map((token) => token.trim())
    .filter(Boolean)
}

export default function GapDashboard({ onAnalyse, status, error, items, suggestions }) {
  const [input, setInput] = useState(suggestions.join(', '))

  const handleSubmit = (event) => {
    event.preventDefault()
    const nodes = parseNodes(input)
    if (!nodes.length) {
      return
    }
    onAnalyse({ focus_nodes: nodes })
  }

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
        <ul className="gap-list" data-testid="gap-results">
          {items.map((gap) => (
            <li key={`${gap.subject}-${gap.object}`}>
              <span className="gap-pair">{gap.subject} → {gap.object}</span>
              <span className="gap-reason">{gap.reason}</span>
            </li>
          ))}
        </ul>
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

