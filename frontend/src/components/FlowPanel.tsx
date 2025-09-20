import { NeuroFlow } from '../api/types';
import ProvenanceCard from './ProvenanceCard';
import './FlowPanel.css';

interface FlowPanelProps {
  title: string;
  direction: 'top-down' | 'bottom-up';
  flows: NeuroFlow[];
  loading?: boolean;
  onRefresh: () => void;
}

const FlowPanel = ({ title, direction, flows, loading = false, onRefresh }: FlowPanelProps) => {
  return (
    <section className="flow-panel" data-direction={direction}>
      <header className="flow-panel__header">
        <div>
          <h2>{title}</h2>
          <p>
            {direction === 'top-down'
              ? 'Trace neurotransmitter initiated cascades toward behaviour.'
              : 'Surface behavioural effects and infer upstream modulators.'}
          </p>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading}>
          Refresh
        </button>
      </header>
      {loading && <p className="flow-panel__status">Loading {direction} flows…</p>}
      {!loading && flows.length === 0 && (
        <p className="flow-panel__status">No flows available with the current filters.</p>
      )}
      <div className="flow-panel__list">
        {flows.map((flow) => (
          <article className="flow-panel__item" key={flow.id} data-testid={`flow-${flow.id}`}>
            <h3>{flow.title}</h3>
            <p className="flow-panel__description">{flow.description}</p>
            <ol className="flow-panel__segments">
              {flow.segments.map((segment, index) => (
                <li key={`${flow.id}-${index}`}>
                  <span>{segment.from}</span>
                  <span className="flow-panel__relation">{segment.relation}</span>
                  <span>{segment.to}</span>
                </li>
              ))}
            </ol>
            <p className="flow-panel__score">Model confidence: {(flow.score * 100).toFixed(0)}%</p>
            <div className="flow-panel__provenance">
              {flow.provenance.map((entry) => (
                <ProvenanceCard key={entry.id} entry={entry} />
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};

export default FlowPanel;
