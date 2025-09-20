import { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import UncertaintyBadge from './UncertaintyBadge'
import './SimulationPanel.css'

const mechanisms = ['agonist', 'antagonist', 'partial', 'inverse']

function formatPercent(value) {
  return `${Math.round(value * 100)}%`
}

export default function SimulationPanel({ effects, simulation, onSimulate, timeIndex, onTimeIndexChange }) {
  const [receptors, setReceptors] = useState({})
  const [dosing, setDosing] = useState('chronic')
  const [acute1a, setAcute1a] = useState(false)
  const [adhd, setAdhd] = useState(false)
  const [gutBias, setGutBias] = useState(false)
  const [pvtWeight, setPvtWeight] = useState(0.5)

  useEffect(() => {
    if (!effects?.length) {
      return
    }
    setReceptors((current) => {
      const next = { ...current }
      effects.forEach((effect) => {
        if (!next[effect.receptor]) {
          next[effect.receptor] = {
            enabled: true,
            occ: 0.5,
            mech: 'agonist',
          }
        }
      })
      return next
    })
  }, [effects])

  const timepoints = simulation.data?.details?.timepoints ?? []
  const trajectories = simulation.data?.details?.trajectories ?? {}
  const receptorContext = simulation.data?.details?.receptor_context ?? {}
  const modules = simulation.data?.details?.modules ?? {}
  const selectedTime = timepoints[timeIndex] ?? timepoints[timepoints.length - 1] ?? 0

  const moduleRows = useMemo(() => {
    if (!modules || !selectedTime) {
      return []
    }
    return Object.entries(modules).map(([moduleKey, moduleValue]) => {
      const rawScore = moduleValue.timeline?.[timeIndex] ?? moduleValue.score ?? 0
      return {
        key: moduleKey,
        description: moduleValue.description ?? moduleKey,
        score: Number(rawScore) || 0,
      }
    })
  }, [modules, timeIndex, selectedTime])

  const handleToggle = (receptor) => {
    setReceptors((current) => ({
      ...current,
      [receptor]: { ...current[receptor], enabled: !current[receptor].enabled },
    }))
  }

  const handleSpecChange = (receptor, field, value) => {
    const nextValue = field === 'occ' ? Number(value) : value
    setReceptors((current) => ({
      ...current,
      [receptor]: { ...current[receptor], [field]: nextValue },
    }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    const payload = {}
    Object.entries(receptors).forEach(([receptor, spec]) => {
      if (spec.enabled) {
        payload[receptor] = {
          occ: Number(spec.occ),
          mech: spec.mech,
        }
      }
    })
    if (!Object.keys(payload).length) {
      return
    }
    onSimulate({
      receptors: payload,
      dosing,
      acute_1a: acute1a,
      adhd,
      gut_bias: gutBias,
      pvt_weight: Number(pvtWeight),
    })
  }

  const totalEnabled = Object.values(receptors).filter((spec) => spec.enabled).length

  return (
    <section className="panel" data-testid="simulation-panel">
      <header>
        <h2>Simulation cockpit</h2>
        <p className="panel-subtitle">
          Configure receptor engagements and run the simulation engine with time slider playback.
        </p>
      </header>
      <form className="simulation-grid" onSubmit={handleSubmit}>
        <div className="receptor-table" data-testid="simulation-receptors">
          <header>
            <h3>Receptors</h3>
            <span className="receptor-count">{totalEnabled} selected</span>
          </header>
          <div className="receptor-rows">
            {effects?.length ? (
              effects.map((effect) => {
                const spec = receptors[effect.receptor]
                if (!spec) {
                  return null
                }
                return (
                  <div key={effect.receptor} className="receptor-row">
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={spec.enabled}
                        onChange={() => handleToggle(effect.receptor)}
                      />
                      <span>{effect.receptor}</span>
                    </label>
                    <div className="receptor-controls">
                      <label>
                        Occupancy
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={spec.occ}
                          onChange={(event) => handleSpecChange(effect.receptor, 'occ', event.target.value)}
                          data-testid={`occupancy-${effect.receptor}`}
                        />
                        <span className="slider-value">{formatPercent(spec.occ)}</span>
                      </label>
                      <label>
                        Mechanism
                        <select
                          value={spec.mech}
                          onChange={(event) => handleSpecChange(effect.receptor, 'mech', event.target.value)}
                          data-testid={`mechanism-${effect.receptor}`}
                        >
                          {mechanisms.map((mech) => (
                            <option key={mech} value={mech}>
                              {mech}
                            </option>
                          ))}
                        </select>
                      </label>
                      <UncertaintyBadge value={receptorContext[effect.receptor]?.uncertainty} />
                    </div>
                  </div>
                )
              })
            ) : (
              <p className="empty">Run receptor scoring to populate simulation inputs.</p>
            )}
          </div>
        </div>
        <div className="simulation-controls">
          <label className="toggle">
            <input type="checkbox" checked={acute1a} onChange={(event) => setAcute1a(event.target.checked)} />
            <span>Acute 5-HT1A clamp</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={adhd} onChange={(event) => setAdhd(event.target.checked)} />
            <span>ADHD cohort</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={gutBias} onChange={(event) => setGutBias(event.target.checked)} />
            <span>Gut-brain bias</span>
          </label>
          <label>
            Dosing regime
            <select value={dosing} onChange={(event) => setDosing(event.target.value)} data-testid="dosing-select">
              <option value="chronic">Chronic</option>
              <option value="acute">Acute</option>
            </select>
          </label>
          <label>
            PVT weight
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={pvtWeight}
              onChange={(event) => setPvtWeight(Number(event.target.value))}
              data-testid="pvt-weight"
            />
            <span className="slider-value">{formatPercent(pvtWeight)}</span>
          </label>
          <button type="submit" className="primary" disabled={simulation.status === 'loading'} data-testid="simulate-button">
            {simulation.status === 'loading' ? 'Simulating…' : 'Run simulation'}
          </button>
          {simulation.error && <p className="form-error" role="alert">{simulation.error.message}</p>}
        </div>
      </form>
      {timepoints.length > 0 && (
        <div className="timeline" data-testid="simulation-timeline">
          <label htmlFor="time-slider">Time</label>
          <input
            id="time-slider"
            type="range"
            min="0"
            max={timepoints.length - 1}
            value={timeIndex}
            onChange={(event) => onTimeIndexChange(Number(event.target.value))}
          />
          <span className="timeline-value">{selectedTime.toFixed(2)} h</span>
        </div>
      )}
      {simulation.data && (
        <div className="simulation-summary" data-testid="simulation-summary">
          <div className="scoreboard">
            {Object.entries(simulation.data.scores ?? {}).map(([metric, score]) => (
              <div key={metric} className="score-item">
                <span className="metric">{metric}</span>
                <span className="value">{score.toFixed(2)}</span>
                <UncertaintyBadge value={simulation.data.uncertainty?.[metric]} />
              </div>
            ))}
          </div>
          <div className="module-table">
            <h3>Module trajectories</h3>
            <table>
              <thead>
                <tr>
                  <th>Module</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {moduleRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.description}</td>
                    <td>{row.score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}

SimulationPanel.propTypes = {
  effects: PropTypes.arrayOf(
    PropTypes.shape({
      receptor: PropTypes.string.isRequired,
    }),
  ),
  simulation: PropTypes.shape({
    status: PropTypes.string,
    error: PropTypes.instanceOf(Error),
    data: PropTypes.shape({
      scores: PropTypes.object,
      details: PropTypes.object,
      uncertainty: PropTypes.object,
    }),
  }).isRequired,
  onSimulate: PropTypes.func.isRequired,
  timeIndex: PropTypes.number,
  onTimeIndexChange: PropTypes.func.isRequired,
}

SimulationPanel.defaultProps = {
  effects: [],
  timeIndex: 0,
}

