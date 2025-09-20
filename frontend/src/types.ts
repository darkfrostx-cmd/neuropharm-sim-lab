export type TemporalProfile = 'acute' | 'chronic';
export type FiringPattern = 'tonic' | 'phasic';

export interface FilterState {
  temporal: TemporalProfile;
  firing: FiringPattern;
  species: string;
  rdocTags: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'neurotransmitter' | 'region' | 'behaviour';
  uncertainty?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  weight?: number;
  provenance?: Provenance;
}

export interface Provenance {
  source: string;
  reference: string;
  notes?: string;
}

export interface FlowSummary {
  neurotransmitter: string;
  region: string;
  behaviour: string;
  confidence: number;
  provenance: Provenance[];
}

export interface GapInsight {
  id: string;
  description: string;
  uncertainty: number;
  suggestedLiterature: string[];
}

export interface GraphResponse {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface EffectPredictionResponse {
  flows: FlowSummary[];
}

export interface ExplanationResponse {
  rationale: string;
  supportingEvidence: Provenance[];
}

export interface GapsResponse {
  gaps: GapInsight[];
}
