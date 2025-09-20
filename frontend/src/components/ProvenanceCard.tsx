import { ProvenanceEntry } from '../api/types';
import './ProvenanceCard.css';

interface ProvenanceCardProps {
  entry: ProvenanceEntry;
}

const ProvenanceCard = ({ entry }: ProvenanceCardProps) => {
  return (
    <article className="provenance-card">
      <header>
        <h4>{entry.source}</h4>
        {entry.date && <time dateTime={entry.date}>{new Date(entry.date).toLocaleDateString()}</time>}
      </header>
      {entry.reference && (
        <p className="provenance-card__reference">
          <a href={entry.reference} target="_blank" rel="noreferrer">
            Reference
          </a>
        </p>
      )}
      {entry.notes && <p className="provenance-card__notes">{entry.notes}</p>}
      <footer>
        <span className="provenance-card__confidence" aria-label="Confidence score">
          Confidence: {(entry.confidence * 100).toFixed(0)}%
        </span>
      </footer>
    </article>
  );
};

export default ProvenanceCard;
