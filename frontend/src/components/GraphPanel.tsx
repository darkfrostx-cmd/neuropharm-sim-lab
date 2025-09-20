import { memo, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { GraphLink, GraphNode } from '../types';
import { UncertaintyBadge } from './UncertaintyBadge';

interface Props {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  onSelectNode: (node: GraphNode | null) => void;
}

const colors: Record<GraphNode['type'], string> = {
  neurotransmitter: '#0ea5e9',
  region: '#6366f1',
  behaviour: '#f97316'
};

export const GraphPanel = memo(({ nodes, links, loading, onSelectNode }: Props) => {
  const graphData = useMemo(
    () => ({
      nodes: nodes.map((node) => ({ ...node })),
      links: links.map((link) => ({ ...link }))
    }),
    [nodes, links]
  );

  return (
    <section className="panel" aria-label="knowledge graph">
      <h2>Knowledge Graph</h2>
      {loading ? <p>Loading graph…</p> : null}
      <div className="graph-container" data-testid="graph-container">
        <ForceGraph2D
          graphData={graphData}
          nodeLabel={(node) => `${node.label}`}
          nodeColor={(node) => colors[(node as GraphNode).type]}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={(link) => ((link as GraphLink).weight ?? 0.5) * 2}
          onNodeClick={(node) => onSelectNode(node as GraphNode)}
          onBackgroundClick={() => onSelectNode(null)}
        />
      </div>
      <div className="flow-list" aria-label="node legend">
        {nodes.map((node) => (
          <div key={node.id} className="flow-item">
            <strong>{node.label}</strong> · {node.type}
            {node.uncertainty !== undefined ? <UncertaintyBadge value={node.uncertainty} /> : null}
          </div>
        ))}
      </div>
    </section>
  );
});

GraphPanel.displayName = 'GraphPanel';
