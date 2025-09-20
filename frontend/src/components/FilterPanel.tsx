import { ChangeEvent } from 'react';
import { FilterState } from '../api/types';
import './FilterPanel.css';

const TAG_OPTIONS = ['tonic', 'phasic'];
const SPECIES_OPTIONS = ['human', 'rodent', 'nonhuman primate'];
const BEHAVIOUR_OPTIONS = [
  'RDoC:PositiveValence',
  'RDoC:CognitiveSystems',
  'RDoC:NegativeValence'
];

export interface FilterPanelProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function timeLabel(value: number): string {
  if (value <= 0.25) {
    return 'Acute';
  }
  if (value >= 0.75) {
    return 'Chronic';
  }
  return 'Subacute';
}

const FilterPanel = ({ filters, onFiltersChange }: FilterPanelProps) => {
  const handleTimeChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = Number(event.target.value) / 100;
    onFiltersChange({ ...filters, timePreference: nextValue });
  };

  const handleToggle = (field: keyof FilterState, value: string) => {
    const current = filters[field] as string[];
    onFiltersChange({
      ...filters,
      [field]: toggleValue(current, value)
    });
  };

  return (
    <section className="filter-panel" aria-label="Filtering controls">
      <header className="filter-panel__header">
        <h2>Model filters</h2>
        <p>Adjust biological context before expanding the knowledge graph.</p>
      </header>

      <div className="filter-panel__section">
        <h3>Time horizon</h3>
        <label className="filter-panel__slider">
          <span>Acute</span>
          <input
            data-testid="time-slider"
            type="range"
            min={0}
            max={100}
            step={10}
            value={Math.round(filters.timePreference * 100)}
            onChange={handleTimeChange}
          />
          <span>Chronic</span>
        </label>
        <p className="filter-panel__hint">Selected: {timeLabel(filters.timePreference)}</p>
      </div>

      <div className="filter-panel__section">
        <h3>Tags</h3>
        <ul>
          {TAG_OPTIONS.map((tag) => (
            <li key={tag}>
              <label>
                <input
                  type="checkbox"
                  checked={filters.tags.includes(tag)}
                  onChange={() => handleToggle('tags', tag)}
                />
                {tag}
              </label>
            </li>
          ))}
        </ul>
      </div>

      <div className="filter-panel__section">
        <h3>Species</h3>
        <ul>
          {SPECIES_OPTIONS.map((option) => (
            <li key={option}>
              <label>
                <input
                  type="checkbox"
                  checked={filters.species.includes(option)}
                  onChange={() => handleToggle('species', option)}
                />
                {option}
              </label>
            </li>
          ))}
        </ul>
      </div>

      <div className="filter-panel__section">
        <h3>RDoC behaviours</h3>
        <ul>
          {BEHAVIOUR_OPTIONS.map((behaviour) => (
            <li key={behaviour}>
              <label>
                <input
                  type="checkbox"
                  checked={filters.behaviours.includes(behaviour)}
                  onChange={() => handleToggle('behaviours', behaviour)}
                />
                {behaviour.replace('RDoC:', '')}
              </label>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};

export default FilterPanel;
