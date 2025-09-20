import { useEffect, useMemo, useState } from 'react'
import GraphExplorer from './components/GraphExplorer'
import CytoscapeView from './components/CytoscapeView'
import ForceGraphView from './components/ForceGraphView'
import NiiVueCanvas from './components/NiiVueCanvas'
import EffectWorkbench from './components/EffectWorkbench'
import GapDashboard from './components/GapDashboard'
import SimulationPanel from './components/SimulationPanel'
import {
  deriveCytoscapeElements,
  deriveForceGraph,
  useExplain,
  useGapFinder,
  useGraphExpand,
  useMemoisedGraph,
  usePredictEffects,
  useSimulation,
} from './hooks/apiHooks'
import './App.css'

function App() {
  const graphAction = useGraphExpand()
  const predictAction = usePredictEffects()
  const explainAction = useExplain()
  const gapAction = useGapFinder()
  const simulationAction = useSimulation()

  const [selectedNode, setSelectedNode] = useState('')
  const [focusKey, setFocusKey] = useState('')
  const [timeIndex, setTimeIndex] = useState(0)

  const graph = useMemoisedGraph(graphAction.data)
  const cytoscapeElements = useMemo(() => deriveCytoscapeElements(graphAction.data), [graphAction.data])
  const forceGraph = useMemo(() => deriveForceGraph(graphAction.data), [graphAction.data])

  useEffect(() => {
    if (graphAction.data?.centre) {
      setSelectedNode(graphAction.data.centre)
      setFocusKey(graphAction.data.centre)
    }
  }, [graphAction.data])

  useEffect(() => {
    if (!selectedNode && graph.nodes.length) {
      setSelectedNode(graph.nodes[0].id)
    }
  }, [graph.nodes, selectedNode])

  useEffect(() => {
    if (simulationAction.data?.details?.timepoints?.length) {
      setTimeIndex(simulationAction.data.details.timepoints.length - 1)
    }
  }, [simulationAction.data])

  const gapSuggestions = useMemo(() => graph.nodes.slice(0, 5).map((node) => node.id), [graph.nodes])

  const defaultReceptors = useMemo(() => {
    if (predictAction.data?.items?.length) {
      return predictAction.data.items.map((item) => item.receptor)
    }
    return focusKey ? [focusKey] : []
  }, [predictAction.data, focusKey])

  const handleExpand = (payload) => {
    graphAction.execute(payload).catch(() => {})
  }

  const handlePredict = (payload) => {
    predictAction.execute(payload).catch(() => {})
  }

  const handleExplain = (payload) => {
    explainAction.execute(payload).catch(() => {})
  }

  const handleGapAnalyse = (payload) => {
    gapAction.execute(payload).catch(() => {})
  }

  const handleSimulate = (payload) => {
    simulationAction.execute(payload).catch(() => {})
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Neuropharm Simulation Lab</h1>
        <p className="tagline">Top-down atlas overlays meet bottom-up receptor simulations.</p>
      </header>
      <main className="app-main">
        <section className="left-column">
          <GraphExplorer
            onExpand={handleExpand}
            status={graphAction.status}
            error={graphAction.error}
            nodes={graph.nodes}
            onSelectNode={(nodeId) => {
              setSelectedNode(nodeId)
              setFocusKey(nodeId)
            }}
          />
          <EffectWorkbench
            onPredict={handlePredict}
            prediction={predictAction}
            onExplain={handleExplain}
            explanation={explainAction}
            defaultReceptors={defaultReceptors}
            onReceptorFocus={(receptor) => setFocusKey(receptor)}
          />
          <GapDashboard
            onAnalyse={handleGapAnalyse}
            status={gapAction.status}
            error={gapAction.error}
            items={gapAction.data?.items ?? []}
            suggestions={gapSuggestions}
          />
          <SimulationPanel
            effects={predictAction.data?.items ?? []}
            simulation={simulationAction}
            onSimulate={handleSimulate}
            timeIndex={timeIndex}
            onTimeIndexChange={setTimeIndex}
          />
        </section>
        <section className="right-column">
          <div className="atlas-stack">
            <div className="atlas-panel">
              <h2>Top-down atlas view</h2>
              <NiiVueCanvas focusKey={focusKey} />
            </div>
            <div className="atlas-panel">
              <h2>Knowledge graph (Cytoscape)</h2>
              <CytoscapeView
                elements={cytoscapeElements}
                selectedId={selectedNode}
                onSelect={(nodeId) => {
                  setSelectedNode(nodeId)
                  setFocusKey(nodeId)
                }}
              />
            </div>
            <div className="atlas-panel">
              <h2>Bottom-up force graph</h2>
              <ForceGraphView
                graph={forceGraph}
                onNodeSelect={(nodeId) => {
                  setSelectedNode(nodeId)
                  setFocusKey(nodeId)
                }}
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App

