import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import SimulationPanel from '../components/SimulationPanel'

describe('SimulationPanel assumption toggles', () => {
  test('submits new assumption flags with descriptive copy', () => {
    const onSimulate = vi.fn()

    render(
      <SimulationPanel
        effects={[{ receptor: 'MOR' }]}
        simulation={{ status: 'idle', error: null, data: null }}
        onSimulate={onSimulate}
        timeIndex={0}
        onTimeIndexChange={() => {}}
      />,
    )

    expect(screen.getByText(/μ-opioid bonding module/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Amplifies social affiliation via hedonic hotspots/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText(/μ-opioid bonding module/i))
    fireEvent.click(screen.getByLabelText(/A2A–D2 heteromer priming/i))
    fireEvent.click(screen.getByLabelText(/α2C cortical gate/i))

    fireEvent.click(screen.getByTestId('simulate-button'))

    expect(onSimulate).toHaveBeenCalledTimes(1)
    const payload = onSimulate.mock.calls[0][0]
    expect(payload.assumptions.mu_opioid_bonding).toBe(true)
    expect(payload.assumptions.a2a_d2_heteromer).toBe(true)
    expect(payload.assumptions.alpha2c_gate).toBe(true)
    expect(payload.assumptions.trkB_facilitation).toBe(true)
    expect(payload.assumptions.alpha2a_hcn_closure).toBe(false)
  })
})
