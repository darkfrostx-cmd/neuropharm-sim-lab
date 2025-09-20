import { useCallback, useEffect, useState } from 'react';
import { fetchGraphExpansion } from '../services/api';
import { FilterState, GraphLink, GraphNode } from '../types';

interface UseGraphDataArgs {
  filters: FilterState;
}

interface GraphDataState {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
}

export function useGraphData({ filters }: UseGraphDataArgs): GraphDataState {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await fetchGraphExpansion(filters);
    setNodes(result.nodes);
    setLinks(result.links);
    setLoading(false);
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  return { nodes, links, loading };
}
