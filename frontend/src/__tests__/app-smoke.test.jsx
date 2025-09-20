import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from '../App'

vi.mock('@niivue/niivue', () => ({
  Niivue: class {
    attachToCanvas() {}
    setSliceType() {}
    loadVolumes() {
      return Promise.resolve()
    }
    destroy() {}
    setCrosshairLocation() {}
    get sliceTypeAxial() {
      return 0
    }
  },
}))

vi.mock('react-force-graph-2d', () => ({
  __esModule: true,
  default: () => <div data-testid="force-graph-mock" />,
}))

vi.mock('react-cytoscapejs', () => ({
  __esModule: true,
  default: () => <div data-testid="cytoscape-mock" />,
}))

vi.mock('../components/NiiVueCanvas.jsx', () => ({
  __esModule: true,
  default: () => <canvas data-testid="niivue-mock" />,
}))

test('renders application heading', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: /Neuropharm Simulation Lab/i })).toBeInTheDocument()
})

