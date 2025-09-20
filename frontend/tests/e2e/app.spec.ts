import { test, expect } from '@playwright/test'

const now = new Date().toISOString()

const graphResponse = {
  centre: 'DRD2',
  nodes: [
    {
      id: 'DRD2',
      name: 'Dopamine receptor D2',
      category: 'biolink:Gene',
      description: 'D2 receptor',
      synonyms: ['D2'],
      xrefs: [],
      attributes: { degree: 4 },
    },
    {
      id: 'SLC6A3',
      name: 'Dopamine transporter',
      category: 'biolink:Gene',
      attributes: { degree: 3 },
    },
    {
      id: 'COMT',
      name: 'Catechol O-methyltransferase',
      category: 'biolink:Gene',
      attributes: { degree: 2 },
    },
  ],
  edges: [
    {
      subject: 'DRD2',
      predicate: 'biolink:positively_regulates',
      object: 'SLC6A3',
      relation: 'RO:0002213',
      knowledge_level: 'predicted',
      confidence: 0.76,
      uncertainty: 0.24,
      publications: [],
      qualifiers: {},
      created_at: now,
    },
    {
      subject: 'SLC6A3',
      predicate: 'biolink:correlated_with',
      object: 'COMT',
      relation: 'RO:0002610',
      knowledge_level: 'observed',
      confidence: 0.6,
      uncertainty: 0.4,
      publications: [],
      qualifiers: {},
      created_at: now,
    },
  ],
}

const predictResponse = {
  items: [
    {
      receptor: 'DRD2',
      kg_weight: 0.82,
      evidence: 0.74,
      affinity: 0.55,
      expression: 0.48,
      evidence_sources: ['KG1', 'KG2'],
      evidence_items: 6,
      uncertainty: 0.26,
    },
    {
      receptor: 'SLC6A3',
      kg_weight: 0.7,
      evidence: 0.6,
      affinity: 0.45,
      expression: 0.35,
      evidence_sources: ['KG1'],
      evidence_items: 4,
      uncertainty: 0.4,
    },
  ],
}

const explainResponse = {
  receptor: 'DRD2',
  canonical_receptor: 'DRD2',
  kg_weight: 0.8,
  evidence: 0.7,
  uncertainty: 0.3,
  provenance: ['KG1'],
  edges: [
    {
      direction: 'upstream',
      edge: graphResponse.edges[0],
      provenance: [
        {
          source: 'PubMed',
          reference: '12345',
          confidence: 0.8,
        },
      ],
    },
  ],
}

const gapsResponse = {
  items: [
    { subject: 'DRD2', object: 'COMT', reason: 'No curated modulation record' },
  ],
}

const simulationResponse = {
  scores: {
    sedation: 0.42,
    alertness: 0.68,
  },
  details: {
    timepoints: [0, 1, 2, 4],
    trajectories: {
      sedation: [0.1, 0.2, 0.3, 0.42],
      alertness: [0.9, 0.85, 0.78, 0.68],
    },
    modules: {
      cortex: {
        description: 'Cortical arousal',
        timeline: [0.1, 0.25, 0.33, 0.4],
      },
      striatum: {
        description: 'Striatal drive',
        timeline: [0.2, 0.35, 0.4, 0.5],
      },
    },
    receptor_context: {
      DRD2: { uncertainty: 0.3 },
      SLC6A3: { uncertainty: 0.45 },
    },
  },
  citations: {
    DRD2: [],
  },
  confidence: {
    sedation: 0.6,
    alertness: 0.7,
  },
  uncertainty: {
    sedation: 0.4,
    alertness: 0.3,
  },
}

test.beforeEach(async ({ page }) => {
  await page.route('**/graph/expand', (route) => route.fulfill({ json: graphResponse }))
  await page.route('**/predict/effects', (route) => route.fulfill({ json: predictResponse }))
  await page.route('**/explain', (route) => route.fulfill({ json: explainResponse }))
  await page.route('**/gaps', (route) => route.fulfill({ json: gapsResponse }))
  await page.route('**/simulate', (route) => route.fulfill({ json: simulationResponse }))
})

test('graph navigation, provenance, gaps and simulation flows render', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('graph-node-input').waitFor()

  const nodeInput = page.getByTestId('graph-node-input')
  await nodeInput.fill('DRD2')
  await page.getByTestId('graph-expand-button').click()
  await expect(page.getByTestId('graph-node-palette')).toContainText('Dopamine transporter')

  await page.getByTestId('predict-button').click()
  await expect(page.getByTestId('provenance-cards')).toContainText('DRD2')
  await expect(page.getByTestId('provenance-cards')).toContainText('Knowledge graph weight')

  await page.getByTestId('explain-button').click()
  await expect(page.getByTestId('explanation-list')).toContainText('upstream')

  await page.getByTestId('gap-input').fill('DRD2, COMT')
  await page.getByTestId('gap-button').click()
  await expect(page.getByTestId('gap-results')).toContainText('No curated modulation record')

  await page.locator('[data-testid="simulate-button"]').scrollIntoViewIfNeeded()
  await page.getByTestId('simulate-button').click()
  await expect(page.getByTestId('simulation-summary')).toContainText('sedation')
  await expect(page.getByTestId('simulation-summary')).toContainText('alertness')

  const slider = page.locator('#time-slider')
  await slider.fill('0')
  await expect(page.getByText(/0.00 h/)).toBeVisible()

  await expect(page.getByTestId('niivue-canvas')).toBeVisible()
  await expect(page.getByTestId('cytoscape-view')).toBeVisible()
  await expect(page.getByTestId('force-graph-view')).toBeVisible()
})
