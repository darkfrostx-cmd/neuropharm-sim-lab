import { useEffect, useState } from 'react'
import PropTypes from 'prop-types'
import './GraphExplorer.css'

export default function GraphExplorer({ onExpand, status, error, nodes, onSelectNode }) {
  const [nodeId, setNodeId] = useState('DRD2')
  const [depth, setDepth] = useState(1)
  const [limit, setLimit] = useState(25)

  useEffect(() => {
    if (nodes.length && !nodes.some((node) => node.id === nodeId)) {
      setNodeId(nodes[0].id)
    }
  }, [nodes, nodeId])

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!nodeId) {
      return
    }
    onExpand({ node_id: nodeId, depth: Number(depth), limit: Number(limit) })
  }

  return (
    <section className="panel" data-testid="graph-explorer">
      <header>
        <h2>Knowledge graph explorer</h2>
        <p className="panel-subtitle">Expand the neighbourhood around a node to drive atlas overlays.</p>
      </header>
      <form className="form-grid" onSubmit={handleSubmit}>
        <label htmlFor="node-id">Node identifier</label>
        <input
          id="node-id"
          name="node"
          value={nodeId}
          onChange={(event) => setNodeId(event.target.value)}
          placeholder="e.g. DRD2"
          data-testid="graph-node-input"
        />
        <label htmlFor="depth">Depth</label>
        <input
          id="depth"
          type="number"
          min="1"
          max="4"
          value={depth}
          onChange={(event) => setDepth(event.target.value)}
          data-testid="graph-depth-input"
        />
        <label htmlFor="limit">Max nodes</label>
        <input
          id="limit"
          type="number"
          min="1"
          max="200"
          value={limit}
          onChange={(event) => setLimit(event.target.value)}
          data-testid="graph-limit-input"
        />
        <button type="submit" className="primary" disabled={status === 'loading'} data-testid="graph-expand-button">
          {status === 'loading' ? 'Expanding…' : 'Expand neighbourhood'}
        </button>
      </form>
      {error && <p className="form-error" role="alert">{error.message}</p>}
      {nodes.length > 0 && (
        <div className="node-palette" data-testid="graph-node-palette">
          {nodes.slice(0, 12).map((node) => (
            <button
              key={node.id}
              type="button"
              className="node-chip"
              onClick={() => {
                setNodeId(node.id)
                if (onSelectNode) {
                  onSelectNode(node.id)
                }
              }}
            >
              <span className="node-name">{node.name || node.id}</span>
              <span className="node-category">{node.category}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

GraphExplorer.propTypes = {
  onExpand: PropTypes.func.isRequired,
  status: PropTypes.string,
  error: PropTypes.instanceOf(Error),
  nodes: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      name: PropTypes.string,
      category: PropTypes.string,
    }),
  ),
  onSelectNode: PropTypes.func,
}

GraphExplorer.defaultProps = {
  status: 'idle',
  error: null,
  nodes: [],
  onSelectNode: undefined,
}

