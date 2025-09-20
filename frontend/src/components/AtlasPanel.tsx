import { useEffect, useRef, useState } from 'react';
import { Niivue } from '@niivue/niivue';
import { FlowSummary } from '../types';
import { UncertaintyBadge } from './UncertaintyBadge';

interface Props {
  selectedFlow: FlowSummary | null;
  explanation: string;
}

export function AtlasPanel({ selectedFlow, explanation }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nvRef = useRef<Niivue | null>(null);
  const [status, setStatus] = useState('initialising');

  useEffect(() => {
    let cancelled = false;

    const initialise = async () => {
      try {
        const nv = new Niivue({ logging: false, loadingText: 'Loading atlas…' });
        nvRef.current = nv;
        if (canvasRef.current) {
          nv.attachToCanvas(canvasRef.current);
          if (!cancelled) {
            setStatus('ready');
          }
        }

        const dims = [2, 2, 2, 1, 1, 1, 1, 1];
        const pixdim = [1, 1, 1, 1, 1, 1, 1, 1];
        const synthetic = new Float32Array([
          0.1, 0.4, 0.6, 0.8,
          0.2, 0.3, 0.7, 0.9
        ]);

        try {
          await nv.loadVolumes([
            {
              id: 'synthetic-atlas',
              hdr: {
                datatypeCode: 16,
                bitpix: 32,
                dim: dims,
                pixDim: pixdim
              },
              image: synthetic
            }
          ] as any);
        } catch (error) {
          console.warn('Falling back to static atlas placeholder', error);
          if (!cancelled) {
            setStatus('fallback');
          }
        }
      } catch (error) {
        console.error('Unable to initialise Niivue, using placeholder atlas.', error);
        if (!cancelled) {
          setStatus('fallback');
        }
      }
    };

    initialise();

    return () => {
      cancelled = true;
      if (nvRef.current) {
        try {
          nvRef.current.clearDrawing?.();
          nvRef.current.drawClear?.();
          nvRef.current.destroyAllMesh?.();
        } catch (error) {
          console.warn('Error while cleaning up Niivue', error);
        }
        nvRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!nvRef.current) return;
    if (!selectedFlow) {
      try {
        nvRef.current.setSliceType?.(nvRef.current.sliceTypeMultiplanar);
      } catch (error) {
        console.warn('Unable to reset Niivue slice type', error);
      }
      return;
    }

    try {
      nvRef.current.setSliceType?.(nvRef.current.sliceTypeRender);
      nvRef.current.setClipPlane?.([0.5, 0.5, 0.5]);
    } catch (error) {
      console.warn('Unable to update Niivue view', error);
    }
    canvasRef.current?.setAttribute('data-active-region', selectedFlow.region);
  }, [selectedFlow]);

  const statusMessage =
    status === 'ready'
      ? `Atlas ready${selectedFlow ? ` · Highlighting ${selectedFlow.region}` : ''}`
      : `Atlas placeholder${selectedFlow ? ` · Highlighting ${selectedFlow.region}` : ''}`;

  return (
    <section className="panel" aria-label="atlas visualisation">
      <h2>Atlas View</h2>
      <p>{explanation}</p>
      <div className="atlas-container">
        <canvas ref={canvasRef} data-testid="atlas-canvas" style={{ width: '100%', height: '100%' }} />
        <p role="status">{statusMessage}</p>
        {selectedFlow ? <UncertaintyBadge value={selectedFlow.confidence} /> : null}
      </div>
    </section>
  );
}
