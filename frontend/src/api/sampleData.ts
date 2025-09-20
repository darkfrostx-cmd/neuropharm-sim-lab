import { FilterState, GapsResponse, GraphData, NeuroFlow } from './types';

export const sampleGraph: GraphData = {
  nodes: [
    { id: 'dopamine', label: 'Dopamine', kind: 'neurotransmitter', importance: 0.9 },
    { id: 'd2r', label: 'D2 Receptor', kind: 'receptor', importance: 0.8 },
    { id: 'cAMP_pathway', label: 'cAMP Pathway', kind: 'pathway', importance: 0.6 },
    { id: 'striatum', label: 'Striatum', kind: 'region', importance: 0.7 },
    { id: 'goal_directed', label: 'Goal Directed Behaviour', kind: 'behaviour', importance: 0.65 },
    { id: 'serotonin', label: 'Serotonin', kind: 'neurotransmitter', importance: 0.55 },
    { id: '5ht2a', label: '5-HT2A Receptor', kind: 'receptor', importance: 0.5 },
    { id: 'prefrontal', label: 'Prefrontal Cortex', kind: 'region', importance: 0.45 },
    { id: 'cognitive_flexibility', label: 'Cognitive Flexibility', kind: 'behaviour', importance: 0.5 }
  ],
  links: [
    { source: 'dopamine', target: 'd2r', relation: 'binds', confidence: 0.92 },
    { source: 'd2r', target: 'cAMP_pathway', relation: 'modulates', confidence: 0.82 },
    { source: 'cAMP_pathway', target: 'striatum', relation: 'expressed_in', confidence: 0.78 },
    { source: 'striatum', target: 'goal_directed', relation: 'supports', confidence: 0.7 },
    { source: 'serotonin', target: '5ht2a', relation: 'binds', confidence: 0.88 },
    { source: '5ht2a', target: 'prefrontal', relation: 'expressed_in', confidence: 0.77 },
    { source: 'prefrontal', target: 'cognitive_flexibility', relation: 'supports', confidence: 0.73 }
  ]
};

export const sampleTopDownFlows: NeuroFlow[] = [
  {
    id: 'td-1',
    title: 'Dopamine to Behaviour',
    description: 'Canonical dopaminergic signalling pathway influencing goal-directed behaviour.',
    direction: 'top-down',
    score: 0.81,
    segments: [
      { from: 'dopamine', to: 'd2r', relation: 'binds' },
      { from: 'd2r', to: 'cAMP_pathway', relation: 'modulates' },
      { from: 'cAMP_pathway', to: 'striatum', relation: 'activates' },
      { from: 'striatum', to: 'goal_directed', relation: 'enables' }
    ],
    provenance: [
      {
        id: 'prov-1',
        source: 'Grace, 2016',
        reference: 'https://doi.org/10.1038/nrn.2016.31',
        notes: 'Review of dopaminergic control in basal ganglia loops.',
        confidence: 0.86,
        date: '2016-04-01'
      },
      {
        id: 'prov-2',
        source: 'Human fMRI meta-analysis',
        notes: 'Enhanced striatal activation linked to goal-directed planning.',
        confidence: 0.74,
        date: '2020-11-20'
      }
    ]
  },
  {
    id: 'td-2',
    title: 'Serotonergic modulation of cognition',
    description: 'Serotonin acting on 5-HT2A receptors promotes prefrontal flexibility.',
    direction: 'top-down',
    score: 0.67,
    segments: [
      { from: 'serotonin', to: '5ht2a', relation: 'binds' },
      { from: '5ht2a', to: 'prefrontal', relation: 'modulates' },
      { from: 'prefrontal', to: 'cognitive_flexibility', relation: 'supports' }
    ],
    provenance: [
      {
        id: 'prov-3',
        source: 'Carhart-Harris et al., 2014',
        reference: 'https://doi.org/10.1073/pnas.1403491111',
        notes: 'Psychedelic-assisted modulation of cognitive flexibility.',
        confidence: 0.69
      }
    ]
  }
];

export const sampleBottomUpFlows: NeuroFlow[] = [
  {
    id: 'bu-1',
    title: 'Behaviour-driven feedback',
    description: 'Behavioural engagement feeds back onto dopaminergic tone via striatal learning signals.',
    direction: 'bottom-up',
    score: 0.59,
    segments: [
      { from: 'goal_directed', to: 'striatum', relation: 'reinforces' },
      { from: 'striatum', to: 'dopamine', relation: 'modulates' }
    ],
    provenance: [
      {
        id: 'prov-4',
        source: 'Schultz, 2019',
        reference: 'https://doi.org/10.7554/eLife.42919',
        notes: 'Reward prediction error dynamics.',
        confidence: 0.62
      }
    ]
  }
];

export const sampleGaps: GapsResponse = {
  updatedAt: '2024-01-10T12:00:00Z',
  gaps: [
    {
      id: 'gap-1',
      label: 'Chronic dopaminergic adaptation',
      description: 'Sparse longitudinal data on chronic D2 receptor downregulation in humans.',
      severity: 0.8,
      uncertainty: 0.9,
      tags: ['chronic', 'human', 'tonic']
    },
    {
      id: 'gap-2',
      label: 'Species translation',
      description: 'Rodent cAMP pathway findings lack primate replication.',
      severity: 0.65,
      uncertainty: 0.7,
      tags: ['rodent', 'pathway']
    },
    {
      id: 'gap-3',
      label: 'Behavioural specificity',
      description: 'Need behavioural assays mapping to RDoC constructs for serotonergic modulation.',
      severity: 0.55,
      uncertainty: 0.6,
      tags: ['RDoC', 'acute']
    }
  ]
};

export const defaultFilters: FilterState = {
  timePreference: 0.5,
  tags: ['tonic', 'phasic'],
  species: ['human'],
  behaviours: ['RDoC:PositiveValence']
};
