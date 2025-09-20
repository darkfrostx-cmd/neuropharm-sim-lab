import { useEffect, useMemo, useState } from 'react';
import { AtlasPanel } from './components/AtlasPanel';
import { FilterPanel } from './components/FilterPanel';
import { FlowPanel } from './components/FlowPanel';
import { GapDashboard } from './components/GapDashboard';
import { GraphPanel } from './components/GraphPanel';
import { useGraphData } from './hooks/useGraphData';
import { fetchExplanation, fetchGaps, fetchPredictedEffects } from './services/api';
import { FilterState, FlowSummary, GapInsight, GraphNode } from './types';

const defaultFilters: FilterState = {
  temporal: 'acute',
  firing: 'tonic',
  species: 'human',
  rdocTags: []
};

function deduplicateFlows(flows: FlowSummary[]): FlowSummary[] {
  const seen = new Set<string>();
  return flows.filter((flow) => {
    const key = `${flow.neurotransmitter}-${flow.region}-${flow.behaviour}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function App() {
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [topDownFlows, setTopDownFlows] = useState<FlowSummary[]>([]);
  const [bottomUpFlows, setBottomUpFlows] = useState<FlowSummary[]>([]);
  const [selectedFlow, setSelectedFlow] = useState<FlowSummary | null>(null);
  const [gaps, setGaps] = useState<GapInsight[]>([]);
  const [explanation, setExplanation] = useState('');

  const { nodes, links, loading } = useGraphData({ filters });

  useEffect(() => {
    let active = true;
    async function load() {
      const [effectsResponse, explanationResponse, gapsResponse] = await Promise.all([
        fetchPredictedEffects(filters),
        fetchExplanation(filters),
        fetchGaps(filters)
      ]);

      if (!active) return;
      const flows = deduplicateFlows(effectsResponse.flows);
      setTopDownFlows(flows);
      setBottomUpFlows([...flows].sort((a, b) => a.behaviour.localeCompare(b.behaviour)));
      setSelectedFlow(flows[0] ?? null);
      setExplanation(explanationResponse.rationale);
      setGaps(gapsResponse.gaps);
    }

    load();
    return () => {
      active = false;
    };
  }, [filters]);

  const description = useMemo(() => {
    const tags = filters.rdocTags.length ? filters.rdocTags.join(', ') : 'all RDoC constructs';
    return `Exploring ${filters.temporal} ${filters.firing} signalling in ${filters.species} models across ${tags}.`;
  }, [filters]);

  const handleNodeSelection = (node: GraphNode | null) => {
    if (!node) {
      setSelectedFlow(null);
      return;
    }

    if (node.type === 'region') {
      const match = topDownFlows.find((flow) => flow.region.toLowerCase() === node.label.toLowerCase());
      if (match) setSelectedFlow(match);
    }

    if (node.type === 'neurotransmitter') {
      const match = topDownFlows.find((flow) => flow.neurotransmitter.toLowerCase() === node.label.toLowerCase());
      if (match) setSelectedFlow(match);
    }

    if (node.type === 'behaviour') {
      const match = topDownFlows.find((flow) => flow.behaviour.toLowerCase() === node.label.toLowerCase());
      if (match) setSelectedFlow(match);
    }
  };

  return (
    <main>
      <header style={{ padding: '1rem 1.5rem' }}>
        <h1>Neuropharm Sim Lab</h1>
        <p>{description}</p>
      </header>
      <div className="panel-grid">
        <FilterPanel filters={filters} onChange={setFilters} />
        <FlowPanel title="Top-down exploration" flows={topDownFlows} selectedFlow={selectedFlow} onSelect={setSelectedFlow} />
        <FlowPanel title="Bottom-up exploration" flows={bottomUpFlows} selectedFlow={selectedFlow} onSelect={setSelectedFlow} />
        <GraphPanel nodes={nodes} links={links} loading={loading} onSelectNode={handleNodeSelection} />
        <AtlasPanel selectedFlow={selectedFlow} explanation={explanation} />
        <GapDashboard gaps={gaps} />
      </div>
    </main>
  );
}
