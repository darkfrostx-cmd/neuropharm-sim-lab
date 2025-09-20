import { FlowSummary } from '../types';
import { ProvenanceCard } from './ProvenanceCard';
import { UncertaintyBadge } from './UncertaintyBadge';

interface Props {
  title: string;
  flows: FlowSummary[];
  selectedFlow: FlowSummary | null;
  onSelect: (flow: FlowSummary) => void;
}

export function FlowPanel({ title, flows, selectedFlow, onSelect }: Props) {
  return (
    <section className="panel" aria-label={`${title} flows`}>
      <h2>{title}</h2>
      <div className="flow-list">
        {flows.map((flow) => {
          const isSelected = selectedFlow?.behaviour === flow.behaviour && selectedFlow?.region === flow.region;
          return (
            <article
              key={`${flow.neurotransmitter}-${flow.region}-${flow.behaviour}`}
              className="flow-item"
              aria-pressed={isSelected}
              tabIndex={0}
              onClick={() => onSelect(flow)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(flow);
                }
              }}
              role="button"
              data-testid="flow-card"
              style={{ borderColor: isSelected ? '#2563eb' : undefined }}
            >
              <header>
                <strong>{flow.neurotransmitter}</strong> → {flow.region} → {flow.behaviour}
              </header>
              <UncertaintyBadge value={1 - flow.confidence} />
              <div className="provenance-list">
                {flow.provenance.map((item) => (
                  <ProvenanceCard key={item.reference} provenance={item} />
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
