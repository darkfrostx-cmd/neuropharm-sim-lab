import { Provenance } from '../types';

interface Props {
  provenance: Provenance;
}

export function ProvenanceCard({ provenance }: Props) {
  return (
    <article className="flow-item" aria-label={`Evidence from ${provenance.source}`}>
      <h4>{provenance.source}</h4>
      <p>
        <strong>Reference:</strong> {provenance.reference}
      </p>
      {provenance.notes && <p>{provenance.notes}</p>}
    </article>
  );
}
