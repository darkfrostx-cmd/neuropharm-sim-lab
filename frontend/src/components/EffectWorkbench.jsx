import { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import UncertaintyBadge from './UncertaintyBadge'
import './EffectWorkbench.css'

function toPayload(value) {
  if (!value.trim()) {
    return []
  }
  return value
    .split(/\n|,/)
    .map((token) => token.trim())
    .filter(Boolean)
    .map((name) => ({ name }))
}

export default function EffectWorkbench({
  onPredict,
  prediction,
  onExplain,
  explanation,
  defaultReceptors,
  onReceptorFocus,
}) {
  const [receptorInput, setReceptorInput] = useState(defaultReceptors.join(', '))
  const [explainTarget, setExplainTarget] = useState(defaultReceptors[0] ?? '')
  const [direction, setDirection] = useState('both')
  const [limit, setLimit] = useState(12)

  useEffect(() => {
    if (defaultReceptors.length) {
      setReceptorInput(defaultReceptors.join(', '))
      setExplainTarget((prev) => prev || defaultReceptors[0])
    }
  }, [defaultReceptors])

  const parsedReceptors = useMemo(() => toPayload(receptorInput), [receptorInput])

  const handlePredict = (event) => {
    event.preventDefault()
    if (!parsedReceptors.length) {
      return
    }
    onPredict({ receptors: parsedReceptors })
    if (onReceptorFocus && parsedReceptors[0]) {
      onReceptorFocus(parsedReceptors[0].name)
    }
  }

  const handleExplain = (event) => {
    event.preventDefault()
    if (!explainTarget) {
      return
    }
    onExplain({ receptor: explainTarget, direction, limit: Number(limit) })
    if (onReceptorFocus) {
      onReceptorFocus(explainTarget)
    }
  }

  return (
    <section className="panel" data-testid="effect-workbench">
      <header>
        <h2>Receptor evidence &amp; explanations</h2>
        <p className="panel-subtitle">
          Generate provenance cards and inspect upstream/downstream edges for receptors of interest.
        </p>
      </header>
      <form className="form-grid" onSubmit={handlePredict}>
        <label htmlFor="receptor-list">Receptors</label>
        <textarea
          id="receptor-list"
          rows="2"
          value={receptorInput}
          onChange={(event) => setReceptorInput(event.target.value)}
          data-testid="receptor-input"
          placeholder="DRD2, HTR1A, SLC6A4"
        />
        <button type="submit" className="primary" disabled={prediction.status === 'loading'} data-testid="predict-button">
          {prediction.status === 'loading' ? 'Scoring…' : 'Score receptor evidence'}
        </button>
      </form>
      {prediction.error && <p className="form-error" role="alert">{prediction.error.message}</p>}
      {prediction.data?.items?.length > 0 && (
        <div className="provenance-grid" data-testid="provenance-cards">
          {prediction.data.items.map((item) => (
            <article key={item.receptor} className="provenance-card">
              <header>
                <h3>{item.receptor}</h3>
                <UncertaintyBadge value={item.uncertainty} />
              </header>
              <dl>
                <div>
                  <dt>Knowledge graph weight</dt>
                  <dd>{item.kg_weight.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Evidence score</dt>
                  <dd>{item.evidence.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Affinity</dt>
                  <dd>{item.affinity != null ? item.affinity.toFixed(2) : 'n/a'}</dd>
                </div>
                <div>
                  <dt>Expression</dt>
                  <dd>{item.expression != null ? item.expression.toFixed(2) : 'n/a'}</dd>
                </div>
                <div>
                  <dt>Sources</dt>
                  <dd>{item.evidence_sources.join(', ') || '—'}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
      <form className="form-grid secondary" onSubmit={handleExplain}>
        <label htmlFor="explain-target">Explain receptor</label>
        <input
          id="explain-target"
          value={explainTarget}
          onChange={(event) => setExplainTarget(event.target.value)}
          placeholder="DRD2"
          data-testid="explain-input"
        />
        <label htmlFor="direction">Direction</label>
        <select
          id="direction"
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          data-testid="explain-direction"
        >
          <option value="both">Both</option>
          <option value="upstream">Upstream</option>
          <option value="downstream">Downstream</option>
        </select>
        <label htmlFor="edge-limit">Edge limit</label>
        <input
          id="edge-limit"
          type="number"
          min="1"
          max="50"
          value={limit}
          onChange={(event) => setLimit(event.target.value)}
          data-testid="explain-limit"
        />
        <button type="submit" className="primary" disabled={explanation.status === 'loading'} data-testid="explain-button">
          {explanation.status === 'loading' ? 'Fetching…' : 'Explain receptor'}
        </button>
      </form>
      {explanation.error && <p className="form-error" role="alert">{explanation.error.message}</p>}
      {explanation.data?.edges?.length > 0 && (
        <div className="explanation-list" data-testid="explanation-list">
          {explanation.data.edges.map((edge) => (
            <article key={`${edge.edge.subject}-${edge.edge.object}-${edge.direction}`} className="explanation-card">
              {edge.direction && (
                <p className="edge-direction">{edge.direction}</p>
              )}
              <header>
                <h4>
                  {edge.direction === 'upstream' ? '⬆️' : '⬇️'} {edge.edge.subject} → {edge.edge.object}
                </h4>
                <UncertaintyBadge value={edge.edge.uncertainty} label="Edge uncertainty" />
              </header>
              <p className="edge-meta">{edge.edge.predicate}</p>
              <p className="edge-context">{edge.provenance.length} provenance items</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

EffectWorkbench.propTypes = {
  onPredict: PropTypes.func.isRequired,
  prediction: PropTypes.shape({
    status: PropTypes.string,
    error: PropTypes.instanceOf(Error),
    data: PropTypes.shape({
      items: PropTypes.arrayOf(
        PropTypes.shape({
          receptor: PropTypes.string.isRequired,
          kg_weight: PropTypes.number.isRequired,
          evidence: PropTypes.number.isRequired,
          affinity: PropTypes.number,
          expression: PropTypes.number,
          evidence_sources: PropTypes.arrayOf(PropTypes.string),
          uncertainty: PropTypes.number,
        }),
      ),
    }),
  }).isRequired,
  onExplain: PropTypes.func.isRequired,
  explanation: PropTypes.shape({
    status: PropTypes.string,
    error: PropTypes.instanceOf(Error),
    data: PropTypes.shape({
      edges: PropTypes.arrayOf(
        PropTypes.shape({
          direction: PropTypes.string,
          edge: PropTypes.shape({
            subject: PropTypes.string,
            object: PropTypes.string,
            predicate: PropTypes.string,
            uncertainty: PropTypes.number,
          }),
        }),
      ),
    }),
  }).isRequired,
  defaultReceptors: PropTypes.arrayOf(PropTypes.string),
  onReceptorFocus: PropTypes.func,
}

EffectWorkbench.defaultProps = {
  defaultReceptors: [],
  onReceptorFocus: undefined,
}

