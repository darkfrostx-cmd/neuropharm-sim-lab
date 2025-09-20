import { ChangeEvent } from 'react';
import { FilterState } from '../types';

interface Props {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
}

const speciesOptions = ['human', 'rat', 'mouse', 'non-human primate'];
const rdocOptions = ['negative valence', 'positive valence', 'cognitive systems', 'arousal', 'social'];

export function FilterPanel({ filters, onChange }: Props) {
  const update = (key: keyof FilterState, value: FilterState[keyof FilterState]) => {
    onChange({ ...filters, [key]: value });
  };

  const toggleRDoc = (tag: string) => {
    const exists = filters.rdocTags.includes(tag);
    update(
      'rdocTags',
      exists ? filters.rdocTags.filter((t) => t !== tag) : [...filters.rdocTags, tag]
    );
  };

  const handleSelect = (event: ChangeEvent<HTMLSelectElement>) => {
    update(event.target.name as keyof FilterState, event.target.value as FilterState[keyof FilterState]);
  };

  return (
    <section className="panel" aria-label="filter configuration">
      <h2>Filters</h2>
      <div className="filters">
        <label>
          Temporal profile
          <select
            name="temporal"
            value={filters.temporal}
            onChange={handleSelect}
            data-testid="temporal-filter"
          >
            <option value="acute">Acute</option>
            <option value="chronic">Chronic</option>
          </select>
        </label>
        <label>
          Firing pattern
          <select
            name="firing"
            value={filters.firing}
            onChange={handleSelect}
            data-testid="firing-filter"
          >
            <option value="tonic">Tonic</option>
            <option value="phasic">Phasic</option>
          </select>
        </label>
        <label>
          Species
          <select name="species" value={filters.species} onChange={handleSelect} data-testid="species-filter">
            {speciesOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <fieldset>
        <legend>RDoC tags</legend>
        <div className="filters">
          {rdocOptions.map((tag) => (
            <label key={tag}>
              <input
                type="checkbox"
                checked={filters.rdocTags.includes(tag)}
                onChange={() => toggleRDoc(tag)}
                data-testid={`rdoc-${tag}`}
              />
              {tag}
            </label>
          ))}
        </div>
      </fieldset>
    </section>
  );
}
