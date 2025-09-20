import { useMemo } from 'react'
import PropTypes from 'prop-types'
import ForceGraph2D from 'react-force-graph-2d'
import './ForceGraphView.css'

function nodeColor(category) {
  if (!category) {
    return '#34d399'
  }
  const palette = ['#34d399', '#60a5fa', '#a855f7', '#f97316', '#f43f5e']
  const hash = Math.abs([...category].reduce((acc, char) => acc * 17 + char.charCodeAt(0), 11))
  return palette[hash % palette.length]
}

export default function ForceGraphView({ graph, onNodeSelect }) {
  const data = useMemo(() => ({
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      category: node.category,
      val: node.value ?? 3,
      color: nodeColor(node.category),
    })),
    links: graph.links.map((link) => ({
      id: link.id,
      source: link.source,
      target: link.target,
      label: link.label,
      confidence: link.confidence,
    })),
  }), [graph])

  return (
    <div className="force-graph-wrapper" data-testid="force-graph-view">
      <ForceGraph2D
        graphData={data}
        nodeLabel={(node) => `${node.name}\n${node.category ?? 'unknown'}`}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={(link) => 2 + (link.confidence ?? 0.3) * 2}
        linkDirectionalParticleSpeed={0.005}
        linkColor={() => 'rgba(129, 199, 212, 0.7)'}
        nodeRelSize={6}
        width={undefined}
        height={undefined}
        backgroundColor="rgba(9, 13, 26, 0.85)"
        onNodeClick={(node) => {
          if (onNodeSelect) {
            onNodeSelect(node.id)
          }
        }}
      />
    </div>
  )
}

ForceGraphView.propTypes = {
  graph: PropTypes.shape({
    nodes: PropTypes.arrayOf(
      PropTypes.shape({
        id: PropTypes.string.isRequired,
        name: PropTypes.string,
        category: PropTypes.string,
        value: PropTypes.number,
      }),
    ),
    links: PropTypes.arrayOf(
      PropTypes.shape({
        id: PropTypes.string,
        source: PropTypes.oneOfType([PropTypes.string, PropTypes.object]).isRequired,
        target: PropTypes.oneOfType([PropTypes.string, PropTypes.object]).isRequired,
        label: PropTypes.string,
        confidence: PropTypes.number,
      }),
    ),
  }),
  onNodeSelect: PropTypes.func,
}

ForceGraphView.defaultProps = {
  graph: { nodes: [], links: [] },
  onNodeSelect: undefined,
}

