import { useMemo } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { GraphData, GraphNode } from '../api/types';
import './GraphExplorer.css';
import { useRef } from 'react';

const KIND_COLOURS: Record<GraphNode['kind'], string> = {
  neurotransmitter: '#8ef1ff',
  receptor: '#89b4ff',
  pathway: '#fab387',
  region: '#a6e3a1',
  behaviour: '#f9e2af'
};

export interface GraphExplorerProps {
  data: GraphData;
  selectedNodeId?: string | null;
  loading?: boolean;
  onSelectNode: (nodeId: string) => void;
  onExpandNode: (nodeId: string) => void;
  onReset: () => void;
}

const GraphExplorer = ({
  data,
  selectedNodeId,
  loading = false,
  onSelectNode,
  onExpandNode,
  onReset
}: GraphExplorerProps) => {
  const graphRef = useRef<ForceGraphMethods>();

  const graphData = useMemo(() => {
    return {
      nodes: data.nodes.map((node) => ({
        ...node,
        name: node.label
      })),
      links: data.links.map((link) => ({ ...link }))
    };
  }, [data]);

  const selectedNode = data.nodes.find((node) => node.id === selectedNodeId);

  const handleExpandClick = () => {
    if (selectedNodeId) {
      onExpandNode(selectedNodeId);
    }
  };

  return (
    <section className="graph-explorer">
      <header className="graph-explorer__header">
        <div>
          <h2>Knowledge graph</h2>
          <p>Navigate neurotransmitter → receptor → pathway → region → behaviour relationships.</p>
        </div>
        <div className="graph-explorer__actions">
          <button type="button" onClick={handleExpandClick} disabled={!selectedNodeId || loading}>
            Expand selection
          </button>
          <button type="button" onClick={onReset} disabled={loading}>
            Reset view
          </button>
        </div>
      </header>
      <div className="graph-explorer__canvas" data-testid="graph-canvas">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeRelSize={6}
          enableNodeDrag={false}
          cooldownTicks={80}
          onNodeClick={(node) => {
            onSelectNode(node.id as string);
          }}
          linkDirectionalParticles={2}
          linkDirectionalParticleSpeed={0.005}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = (node as GraphNode & { name: string }).label ?? node.id;
            const kind = (node as GraphNode).kind;
            const baseRadius = 6 + ((node as GraphNode).importance ?? 0) * 8;
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, baseRadius, 0, 2 * Math.PI, false);
            ctx.fillStyle = KIND_COLOURS[kind] ?? '#cdd6f4';
            ctx.fill();
            if (selectedNodeId === node.id) {
              ctx.lineWidth = 2;
              ctx.strokeStyle = '#f38ba8';
              ctx.stroke();
            }
            ctx.font = `${12 / globalScale}px 'Inter', sans-serif`;
            ctx.fillStyle = '#e2e8f0';
            ctx.fillText(label, (node.x ?? 0) + baseRadius + 2, node.y ?? 0);
          }}
        />
      </div>
      {selectedNode && (
        <footer className="graph-explorer__footer">
          <h3>Selected node</h3>
          <dl>
            <div>
              <dt>Label</dt>
              <dd>{selectedNode.label}</dd>
            </div>
            <div>
              <dt>Type</dt>
              <dd>{selectedNode.kind}</dd>
            </div>
            {selectedNode.importance && (
              <div>
                <dt>Importance</dt>
                <dd>{Math.round(selectedNode.importance * 100)}%</dd>
              </div>
            )}
          </dl>
        </footer>
      )}
    </section>
  );
};

export default GraphExplorer;
