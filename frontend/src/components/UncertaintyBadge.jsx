import PropTypes from 'prop-types'
import './UncertaintyBadge.css'

function determineLevel(value) {
  if (value == null || Number.isNaN(value)) {
    return 'unknown'
  }
  if (value < 0.2) {
    return 'low'
  }
  if (value < 0.5) {
    return 'moderate'
  }
  if (value < 0.75) {
    return 'elevated'
  }
  return 'high'
}

function format(value) {
  if (value == null || Number.isNaN(value)) {
    return 'n/a'
  }
  return `${Math.round(value * 100)}%`
}

export default function UncertaintyBadge({ value, label = 'Uncertainty' }) {
  const level = determineLevel(value)
  return (
    <span className={`uncertainty-badge uncertainty-${level}`} data-testid="uncertainty-badge">
      <span className="uncertainty-label">{label}</span>
      <span className="uncertainty-value">{format(value)}</span>
    </span>
  )
}

UncertaintyBadge.propTypes = {
  value: PropTypes.number,
  label: PropTypes.string,
}

