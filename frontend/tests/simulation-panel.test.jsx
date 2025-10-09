import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import SimulationPanel from '../src/components/SimulationPanel.jsx'

const baseSimulation = {
  status: 'idle',
  data: {
    scores: {},
    details: { timepoints: [], trajectories: {}, modules: {}, receptor_context: {} },
    behavioral_tags: {},
  },
}

describe('SimulationPanel advanced assumptions', () => {
  it('submits social-process toggles in the payload', () => {
    const onSimulate = vi.fn()
    render(
      <SimulationPanel
        effects={[{ receptor: '5-HT2A' }]}
        simulation={baseSimulation}
        onSimulate={onSimulate}
        timeIndex={0}
        onTimeIndexChange={() => {}}
      />,
    )

    fireEvent.click(screen.getByRole('checkbox', { name: 'BLA cholinergic salience' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Oxytocin prosocial boost' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Vasopressin threat gating' }))

    fireEvent.click(screen.getByTestId('simulate-button'))

    expect(onSimulate).toHaveBeenCalledTimes(1)
    const payload = onSimulate.mock.calls[0][0]
    expect(payload.assumptions).toMatchObject({
      bla_cholinergic_salience: true,
      oxytocin_prosocial: true,
      vasopressin_gating: true,
    })
  })
})

