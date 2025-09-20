import { GapInsight } from '../types';
import { deriveGapSeverityColor, summariseGap } from '../services/api';

interface Props {
  gaps: GapInsight[];
}

export function GapDashboard({ gaps }: Props) {
  return (
    <section className="panel" aria-label="uncertainty and evidence gaps">
      <h2>Gaps &amp; Suggested Literature</h2>
      <p>
        Track uncertainty hot-spots and launch rapid literature reviews directly from knowledge graph exploration.
      </p>
      <div className="gap-list">
        {gaps.map((gap) => (
          <article
            key={gap.id}
            className="gap-card"
            style={{ backgroundColor: deriveGapSeverityColor(gap.uncertainty) }}
            data-testid="gap-card"
          >
            <header>
              <strong>{summariseGap(gap)}</strong>
            </header>
            <ul>
              {gap.suggestedLiterature.map((item) => (
                <li key={item}>
                  <a href={`https://doi.org/${item.replace('doi:', '')}`} target="_blank" rel="noreferrer">
                    {item}
                  </a>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
