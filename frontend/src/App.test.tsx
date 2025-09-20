import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import App from './App';

vi.mock('@niivue/niivue', () => ({
  Niivue: class {
    sliceTypeMultiplanar = 'multi';
    sliceTypeRender = 'render';
    attachToCanvas() {}
    loadVolumes() {
      return Promise.resolve();
    }
    setSliceType() {}
    setClipPlane() {}
    clearDrawing() {}
    drawClear() {}
    destroyAllMesh() {}
  }
}));

vi.mock('react-force-graph-2d', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-force-graph" />
}));

describe('App integration', () => {
  beforeEach(() => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('network disabled'));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders knowledge exploration panels and updates filters', async () => {
    render(<App />);

    const flowCards = await screen.findAllByTestId('flow-card');
    expect(flowCards.length).toBeGreaterThan(0);

    const description = await screen.findByText(/Exploring acute tonic signalling/i);
    expect(description).toBeInTheDocument();

    const speciesFilter = screen.getByTestId('species-filter');
    await userEvent.selectOptions(speciesFilter, 'rat');

    expect(await screen.findByText(/rat models/)).toBeInTheDocument();
  });

  it('highlights atlas view when selecting a flow and shows gap cards', async () => {
    render(<App />);

    await userEvent.click((await screen.findAllByTestId('flow-card'))[1]);

    await waitFor(() => {
      const cards = screen.getAllByTestId('flow-card');
      expect(cards[1].getAttribute('aria-pressed')).toBe('true');
    });

    await waitFor(() => {
      const statuses = screen.getAllByRole('status').map((status) => status.textContent ?? '');
      expect(statuses.some((text) => text.includes('Prefrontal Cortex'))).toBe(true);
    });

    await waitFor(() => {
      const atlasCanvases = screen.getAllByTestId('atlas-canvas');
      expect(
        atlasCanvases.some((canvas) => canvas.getAttribute('data-active-region') === 'Prefrontal Cortex')
      ).toBe(true);
    });

    const gaps = await screen.findAllByTestId('gap-card');
    expect(gaps.length).toBeGreaterThan(0);
  });
});
