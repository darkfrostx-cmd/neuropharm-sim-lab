import { useCallback, useEffect, useMemo, useState } from 'react';
import FilterPanel from './components/FilterPanel';
import GraphExplorer from './components/GraphExplorer';
import FlowPanel from './components/FlowPanel';
import AtlasViewer from './components/AtlasViewer';
import GapsDashboard from './components/GapsDashboard';
import {
  defaultFilters,
  sampleGraph,
  sampleTopDownFlows,
  sampleBottomUpFlows,
  sampleGaps
} from './api/sampleData';
import {
  FilterState,
  GraphData,
  NeuroFlow,
  GapsResponse
} from './api/types';
import { fetchGraphExpansion, fetchPredictEffects, fetchGaps } from './api';
import './styles/app.css';

const App = () => {
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [graphData, setGraphData] = useState<GraphData>(sampleGraph);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    sampleGraph.nodes[0]?.id ?? null
  );
  const [topDownFlows, setTopDownFlows] = useState<NeuroFlow[]>(sampleTopDownFlows);
  const [bottomUpFlows, setBottomUpFlows] = useState<NeuroFlow[]>(sampleBottomUpFlows);
  const [gaps, setGaps] = useState<GapsResponse>(sampleGaps);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingTopDown, setLoadingTopDown] = useState(false);
  const [loadingBottomUp, setLoadingBottomUp] = useState(false);
  const [loadingGaps, setLoadingGaps] = useState(false);

  const currentRegion = useMemo(() => {
    return graphData.nodes.find((node) => node.id === selectedNodeId && node.kind === 'region')?.label ?? null;
  }, [graphData, selectedNodeId]);

  const loadGraph = useCallback(
    async (focusNode?: string) => {
      setLoadingGraph(true);
      const result = await fetchGraphExpansion({
        focusNode,
        depth: 2,
        filters
      });
      setGraphData(result);
      setLoadingGraph(false);
      if (focusNode && !result.nodes.some((node) => node.id === focusNode)) {
        setSelectedNodeId(result.nodes[0]?.id ?? null);
      }
    },
    [filters]
  );

  const loadFlows = useCallback(async () => {
    if (!selectedNodeId) {
      setTopDownFlows([]);
      setBottomUpFlows([]);
      return;
    }
    setLoadingTopDown(true);
    setLoadingBottomUp(true);
    const [topDown, bottomUp] = await Promise.all([
      fetchPredictEffects({
        direction: 'top-down',
        focusNode: selectedNodeId,
        filters
      }),
      fetchPredictEffects({
        direction: 'bottom-up',
        focusNode: selectedNodeId,
        filters
      })
    ]);
    setTopDownFlows(topDown);
    setBottomUpFlows(bottomUp);
    setLoadingTopDown(false);
    setLoadingBottomUp(false);
  }, [filters, selectedNodeId]);

  const loadGaps = useCallback(async () => {
    setLoadingGaps(true);
    const result = await fetchGaps({ filters });
    setGaps(result);
    setLoadingGaps(false);
  }, [filters]);

  useEffect(() => {
    loadGraph(selectedNodeId ?? undefined);
  }, [loadGraph, selectedNodeId]);

  useEffect(() => {
    loadFlows();
  }, [loadFlows]);

  useEffect(() => {
    loadGaps();
  }, [loadGaps]);

  const handleResetGraph = () => {
    setGraphData(sampleGraph);
    const defaultId = sampleGraph.nodes[0]?.id ?? null;
    setSelectedNodeId(defaultId);
    if (defaultId) {
      loadGraph(defaultId);
    }
  };

  const handleExpand = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    loadGraph(nodeId);
  };

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <h1>Neuropharm Simulation Lab</h1>
        <p>
          Explore neurotransmitter → receptor → pathway → region → behaviour cascades with
          provenance-aware evidence tracking.
        </p>
      </header>
      <main className="app-shell__main">
        <aside className="app-shell__sidebar">
          <FilterPanel filters={filters} onFiltersChange={setFilters} />
          <AtlasViewer selectedRegion={currentRegion} />
        </aside>
        <section className="app-shell__content">
          <GraphExplorer
            data={graphData}
            selectedNodeId={selectedNodeId}
            loading={loadingGraph}
            onSelectNode={setSelectedNodeId}
            onExpandNode={handleExpand}
            onReset={handleResetGraph}
          />
          <div className="app-shell__flows">
            <FlowPanel
              title="Top-down reasoning"
              direction="top-down"
              flows={topDownFlows}
              loading={loadingTopDown}
              onRefresh={loadFlows}
            />
            <FlowPanel
              title="Bottom-up reasoning"
              direction="bottom-up"
              flows={bottomUpFlows}
              loading={loadingBottomUp}
              onRefresh={loadFlows}
            />
          </div>
          <GapsDashboard data={gaps} loading={loadingGaps} onRefresh={loadGaps} />
        </section>
      </main>
    </div>
  );
};

export default App;
