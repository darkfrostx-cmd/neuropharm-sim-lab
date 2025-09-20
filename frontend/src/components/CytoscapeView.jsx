import { useEffect, useMemo, useRef } from 'react'
import PropTypes from 'prop-types'
import CytoscapeComponent from 'react-cytoscapejs'
import './CytoscapeView.css'

const layout = {
  name: 'cose',
  fit: true,
  padding: 20,
  animate: false,
}

const stylesheet = [
  {
    selector: 'node',
    style: {
      'background-color': 'data(color)',
      label: 'data(label)',
      color: '#f5f5f5',
      'font-size': '10px',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': '120px',
      'border-width': 2,
      'border-color': '#1e3a8a',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 2,
      'line-color': '#8ecae6',
      'target-arrow-color': '#8ecae6',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      opacity: 0.75,
      label: 'data(label)',
      'font-size': '8px',
      color: '#bbdefb',
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-width': 6,
      'border-color': '#f97316',
      'shadow-blur': 16,
      'shadow-color': 'rgba(249, 115, 22, 0.55)',
      'shadow-opacity': 0.8,
    },
  },
]

const categoryPalette = [
  '#5a6acf',
  '#8b5cf6',
  '#ec4899',
  '#0ea5e9',
  '#22c55e',
  '#f59e0b',
]

function assignColor(category, index) {
  if (!category) {
    return categoryPalette[index % categoryPalette.length]
  }
  const hash = Math.abs([...category].reduce((acc, char) => acc * 33 + char.charCodeAt(0), 7))
  return categoryPalette[hash % categoryPalette.length]
}

export default function CytoscapeView({ elements, selectedId, onSelect }) {
  const cyRef = useRef(null)
  const enrichedElements = useMemo(
    () =>
      elements.map((element, idx) =>
        element.data?.id
          ? {
              ...element,
              data: {
                ...element.data,
                color: assignColor(element.data.category, idx),
              },
            }
          : element,
      ),
    [elements],
  )

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) {
      return
    }
    cy.off('tap')
    cy.on('tap', 'node', (event) => {
      const nodeId = event.target.id()
      if (onSelect) {
        onSelect(nodeId)
      }
    })
  }, [onSelect])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) {
      return
    }
    cy.nodes().unselect()
    if (selectedId) {
      const node = cy.getElementById(selectedId)
      if (node) {
        node.select()
        cy.animate({ center: { eles: node } }, { duration: 250 })
      }
    }
  }, [selectedId])

  return (
    <div className="cytoscape-wrapper" data-testid="cytoscape-view">
      <CytoscapeComponent
        cy={(cy) => {
          cyRef.current = cy
        }}
        elements={enrichedElements}
        layout={layout}
        stylesheet={stylesheet}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}

CytoscapeView.propTypes = {
  elements: PropTypes.arrayOf(
    PropTypes.shape({
      data: PropTypes.shape({
        id: PropTypes.string,
        label: PropTypes.string,
        category: PropTypes.string,
      }),
    }),
  ),
  selectedId: PropTypes.string,
  onSelect: PropTypes.func,
}

CytoscapeView.defaultProps = {
  elements: [],
  selectedId: null,
  onSelect: undefined,
}

