import { GapsResponse } from '../api/types';
import './GapsDashboard.css';

interface GapsDashboardProps {
  data: GapsResponse | null;
  loading?: boolean;
  onRefresh: () => void;
}

const GapsDashboard = ({ data, loading = false, onRefresh }: GapsDashboardProps) => {
  return (
    <section className="gaps-dashboard">
      <header>
        <div>
          <h2>Evidence gaps</h2>
          <p>Identify domains where knowledge is sparse or uncertain.</p>
          {data?.updatedAt && (
            <p className="gaps-dashboard__timestamp">
              Updated {new Date(data.updatedAt).toLocaleString()}
            </p>
          )}
        </div>
        <button type="button" onClick={onRefresh} disabled={loading}>
          Refresh gaps
        </button>
      </header>
      {loading && <p className="gaps-dashboard__status">Loading evidence gaps…</p>}
      {!loading && !data && <p className="gaps-dashboard__status">No gap summary available.</p>}
      {!loading && data && (
        <div className="gaps-dashboard__grid">
          {data.gaps.map((gap) => (
            <article key={gap.id} className="gaps-dashboard__card" data-testid={`gap-${gap.id}`}>
              <header>
                <h3>{gap.label}</h3>
                <span className="gaps-dashboard__tags">{gap.tags.join(', ')}</span>
              </header>
              <p>{gap.description}</p>
              <div className="gaps-dashboard__metrics">
                <div>
                  <span>Severity</span>
                  <div className="gaps-dashboard__bar">
                    <div style={{ width: `${gap.severity * 100}%` }} />
                  </div>
                  <strong>{(gap.severity * 100).toFixed(0)}%</strong>
                </div>
                <div>
                  <span>Uncertainty</span>
                  <div className="gaps-dashboard__bar">
                    <div className="is-uncertainty" style={{ width: `${gap.uncertainty * 100}%` }} />
                  </div>
                  <strong>{(gap.uncertainty * 100).toFixed(0)}%</strong>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default GapsDashboard;
