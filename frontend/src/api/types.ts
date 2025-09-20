export type NodeKind =
  | 'neurotransmitter'
  | 'receptor'
  | 'pathway'
  | 'region'
  | 'behaviour';

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  importance?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  confidence?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface ProvenanceEntry {
  id: string;
  source: string;
  reference?: string;
  notes?: string;
  confidence: number;
  date?: string;
}

export interface FlowSegment {
  from: string;
  to: string;
  relation: string;
}

export interface NeuroFlow {
  id: string;
  title: string;
  description: string;
  direction: 'top-down' | 'bottom-up';
  score: number;
  segments: FlowSegment[];
  provenance: ProvenanceEntry[];
}

export interface GapsRecord {
  id: string;
  label: string;
  description: string;
  severity: number;
  uncertainty: number;
  tags: string[];
}

export interface GapsResponse {
  updatedAt: string;
  gaps: GapsRecord[];
}

export interface FilterState {
  timePreference: number; // 0 acute, 1 chronic
  tags: string[];
  species: string[];
  behaviours: string[];
}

export interface GraphExpandRequest {
  focusNode?: string;
  depth?: number;
  filters: FilterState;
}

export interface PredictEffectsRequest {
  direction: 'top-down' | 'bottom-up';
  focusNode?: string;
  filters: FilterState;
}

export interface GapsRequest {
  filters: FilterState;
}
