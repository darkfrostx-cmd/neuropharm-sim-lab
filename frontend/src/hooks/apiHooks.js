import { useCallback, useMemo, useState } from 'react'
import { get, post } from '../api/client'

const endpoints = {
  expand: '/graph/expand',
  predict: '/predict/effects',
  explain: '/explain',
  gaps: '/gaps',
  simulate: '/simulate',
}

function normaliseError(err) {
  if (!err) {
    return null
  }
  if (err instanceof Error) {
    return err
  }
  const error = new Error(typeof err === 'string' ? err : 'Request failed')
  return error
}

function useApiAction(endpoint) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState('idle')

  const execute = useCallback(
    async (payload) => {
      setStatus('loading')
      setError(null)
      try {
        const result = await post(endpoint, payload)
        setData(result)
        setStatus('success')
        return result
      } catch (err) {
        const normalised = normaliseError(err)
        setError(normalised)
        setStatus('error')
        throw normalised
      }
    },
    [endpoint],
  )

  const reset = useCallback(() => {
    setStatus('idle')
    setError(null)
    setData(null)
  }, [])

  return { data, error, status, execute, reset }
}

export function useGraphExpand() {
  return useApiAction(endpoints.expand)
}

export function usePredictEffects() {
  return useApiAction(endpoints.predict)
}

export function useExplain() {
  return useApiAction(endpoints.explain)
}

export function useGapFinder() {
  return useApiAction(endpoints.gaps)
}

export function useSimulation() {
  return useApiAction(endpoints.simulate)
}

export function useAtlasOverlay() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const fetchOverlay = useCallback(async (nodeId) => {
    if (!nodeId) {
      setData(null)
      return null
    }
    setStatus('loading')
    setError(null)
    try {
      const result = await get(`/atlas/overlays/${encodeURIComponent(nodeId)}`)
      setData(result)
      setStatus('success')
      return result
    } catch (err) {
      const normalised = normaliseError(err)
      setError(normalised)
      setStatus('error')
      throw normalised
    }
  }, [])

  const reset = useCallback(() => {
    setData(null)
    setStatus('idle')
    setError(null)
  }, [])

  return { data, status, error, fetch: fetchOverlay, reset }
}

export function deriveForceGraph(data) {
  if (!data) {
    return { nodes: [], links: [] }
  }
  const nodes = data.nodes?.map((node) => ({
    id: node.id,
    name: node.name || node.id,
    category: node.category,
    value: (node.attributes?.degree ?? 1) + 1,
  })) ?? []
  const links = data.edges?.map((edge, idx) => ({
    id: `${edge.subject}-${edge.object}-${idx}`,
    source: edge.subject,
    target: edge.object,
    label: edge.predicate,
    confidence: edge.confidence ?? 0.5,
    uncertainty: edge.uncertainty ?? (edge.confidence != null ? 1 - edge.confidence : 0.5),
  })) ?? []
  return { nodes, links }
}

export function deriveCytoscapeElements(data) {
  if (!data) {
    return []
  }
  const nodeElements = data.nodes?.map((node) => ({
    data: {
      id: node.id,
      label: node.name || node.id,
      category: node.category,
    },
  })) ?? []
  const edgeElements = data.edges?.map((edge, idx) => ({
    data: {
      id: `${edge.subject}-${edge.object}-${idx}`,
      source: edge.subject,
      target: edge.object,
      label: edge.predicate,
      confidence: edge.confidence,
      uncertainty: edge.uncertainty,
    },
  })) ?? []
  return [...nodeElements, ...edgeElements]
}

export function useMemoisedGraph(data) {
  return useMemo(() => ({
    nodes: data?.nodes ?? [],
    edges: data?.edges ?? [],
  }), [data])
}

