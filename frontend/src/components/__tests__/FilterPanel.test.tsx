import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FilterPanel from '../FilterPanel';
import { FilterState } from '../../api/types';

describe('FilterPanel', () => {
  const baseFilters: FilterState = {
    timePreference: 0.5,
    tags: ['tonic'],
    species: ['human'],
    behaviours: []
  };

  it('invokes onFiltersChange when the time slider is moved', () => {
    const onFiltersChange = vi.fn();
    render(<FilterPanel filters={baseFilters} onFiltersChange={onFiltersChange} />);

    const slider = screen.getByTestId('time-slider');
    fireEvent.change(slider, { target: { value: '100' } });

    expect(onFiltersChange).toHaveBeenCalledWith({
      ...baseFilters,
      timePreference: 1
    });
  });

  it('toggles tag filters', () => {
    const onFiltersChange = vi.fn();
    render(<FilterPanel filters={baseFilters} onFiltersChange={onFiltersChange} />);

    const phasicCheckbox = screen.getByLabelText('phasic');
    fireEvent.click(phasicCheckbox);

    expect(onFiltersChange).toHaveBeenCalledWith({
      ...baseFilters,
      tags: ['tonic', 'phasic']
    });
  });
});
