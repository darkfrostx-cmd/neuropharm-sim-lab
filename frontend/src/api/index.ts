import {
  GraphData,
  GraphExpandRequest,
  PredictEffectsRequest,
  NeuroFlow,
  GapsResponse,
  GapsRequest
} from './types';
import {
  sampleGraph,
  sampleTopDownFlows,
  sampleBottomUpFlows,
  sampleGaps
} from './sampleData';

const JSON_HEADERS = {
  'Content-Type': 'application/json'
};

async function fetchWithFallback<T>(
  url: string,
  init: RequestInit,
  fallback: T
): Promise<T> {
  try {
    const response = await fetch(url, init);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const data = (await response.json()) as T;
    return data;
  } catch (error) {
    console.warn(`Falling back to sample data for ${url}:`, error);
    return fallback;
  }
}

export async function fetchGraphExpansion(
  request: GraphExpandRequest
): Promise<GraphData> {
  return fetchWithFallback<GraphData>(
    '/graph/expand',
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(request)
    },
    sampleGraph
  );
}

export async function fetchPredictEffects(
  request: PredictEffectsRequest
): Promise<NeuroFlow[]> {
  const fallback = request.direction === 'top-down' ? sampleTopDownFlows : sampleBottomUpFlows;
  return fetchWithFallback<NeuroFlow[]>(
    '/predict/effects',
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(request)
    },
    fallback
  );
}

export async function fetchGaps(request: GapsRequest): Promise<GapsResponse> {
  return fetchWithFallback<GapsResponse>(
    '/gaps',
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(request)
    },
    sampleGaps
  );
}
