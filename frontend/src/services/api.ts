import {
  EffectPredictionResponse,
  ExplanationResponse,
  FilterState,
  GapInsight,
  GapsResponse,
  GraphLink,
  GraphNode,
  GraphResponse,
  Provenance
} from '../types';

interface RequestOptions {
  method?: string;
  body?: unknown;
}

async function requestWithFallback<T>(
  endpoint: string,
  options: RequestOptions,
  fallback: T
): Promise<T> {
  try {
    const response = await fetch(endpoint, {
      method: options.method ?? 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: options.body ? JSON.stringify(options.body) : undefined
    });

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    return (await response.json()) as T;
  } catch (error) {
    console.warn(`Falling back to mock data for ${endpoint}:`, error);
    return fallback;
  }
}

const mockProvenance: Provenance[] = [
  {
    source: 'NeuroAtlas 2024',
    reference: 'doi:10.1000/neuro.2024.001',
    notes: 'Simulated dataset for offline development.'
  }
];

const mockNodes: GraphNode[] = [
  { id: 'dopamine', label: 'Dopamine', type: 'neurotransmitter', uncertainty: 0.1 },
  { id: 'ventral_striatum', label: 'Ventral Striatum', type: 'region', uncertainty: 0.25 },
  { id: 'reward_learning', label: 'Reward Learning', type: 'behaviour', uncertainty: 0.4 }
];

const mockLinks: GraphLink[] = [
  {
    source: 'dopamine',
    target: 'ventral_striatum',
    weight: 0.85,
    provenance: mockProvenance[0]
  },
  {
    source: 'ventral_striatum',
    target: 'reward_learning',
    weight: 0.68,
    provenance: mockProvenance[0]
  }
];

const mockFlows: EffectPredictionResponse = {
  flows: [
    {
      neurotransmitter: 'Dopamine',
      region: 'Ventral Striatum',
      behaviour: 'Reward Learning',
      confidence: 0.76,
      provenance: mockProvenance
    },
    {
      neurotransmitter: 'Serotonin',
      region: 'Prefrontal Cortex',
      behaviour: 'Cognitive Control',
      confidence: 0.52,
      provenance: mockProvenance
    }
  ]
};

const mockExplanation: ExplanationResponse = {
  rationale:
    'Predicted modulation of ventral striatum activity by dopamine aligns with chronic tonic signalling patterns.',
  supportingEvidence: mockProvenance
};

const mockGaps: GapsResponse = {
  gaps: [
    {
      id: 'gap-1',
      description: 'Sparse chronic phasic data linking serotonin to prefrontal microcircuits.',
      uncertainty: 0.62,
      suggestedLiterature: ['doi:10.1000/microcircuits.2023.004']
    },
    {
      id: 'gap-2',
      description: 'Limited behavioural studies connecting ventral striatum reward models to RDoC positive valence.',
      uncertainty: 0.47,
      suggestedLiterature: ['doi:10.1000/rdoc.2022.010']
    }
  ]
};

export async function fetchGraphExpansion(filters: FilterState): Promise<GraphResponse> {
  return requestWithFallback<GraphResponse>(
    '/graph/expand',
    { body: { filters } },
    { nodes: mockNodes, links: mockLinks }
  );
}

export async function fetchPredictedEffects(filters: FilterState): Promise<EffectPredictionResponse> {
  return requestWithFallback<EffectPredictionResponse>(
    '/predict/effects',
    { body: { filters } },
    mockFlows
  );
}

export async function fetchExplanation(filters: FilterState): Promise<ExplanationResponse> {
  return requestWithFallback<ExplanationResponse>(
    '/explain',
    { body: { filters } },
    mockExplanation
  );
}

export async function fetchGaps(filters: FilterState): Promise<GapsResponse> {
  return requestWithFallback<GapsResponse>(
    '/gaps',
    { body: { filters } },
    mockGaps
  );
}

export function deriveGapSeverityColor(uncertainty: number): string {
  if (uncertainty > 0.66) return '#ef4444';
  if (uncertainty > 0.33) return '#f59e0b';
  return '#22c55e';
}

export function summariseGap(gap: GapInsight): string {
  const level = gap.uncertainty > 0.66 ? 'High uncertainty' : gap.uncertainty > 0.33 ? 'Moderate uncertainty' : 'Low uncertainty';
  return `${level}: ${gap.description}`;
}
