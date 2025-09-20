import { useEffect, useRef } from 'react';
import { Niivue } from '@niivue/niivue';
import './AtlasViewer.css';

const DEFAULT_VOLUME_URL = 'https://niivue.github.io/niivue/images/mni152.nii.gz';

interface AtlasViewerProps {
  selectedRegion?: string | null;
}

const AtlasViewer = ({ selectedRegion }: AtlasViewerProps) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const nv = new Niivue({
      logging: false,
      show3Dcrosshair: true,
      showControls: true,
      dragMode: 'slice'
    });

    nv.attachToCanvas(canvas);
    nv
      .loadVolumes([
        {
          url: DEFAULT_VOLUME_URL,
          name: 'MNI152 atlas'
        }
      ])
      .catch((error) => {
        console.warn('Unable to load default atlas volume', error);
      });

    return () => {
      if (typeof (nv as unknown as { destroy?: () => void }).destroy === 'function') {
        (nv as unknown as { destroy: () => void }).destroy();
      }
    };
  }, []);

  return (
    <section className="atlas-viewer">
      <header>
        <h2>Atlas viewer</h2>
        <p>Inspect anatomical context for the current focus region.</p>
      </header>
      <canvas ref={canvasRef} className="atlas-viewer__canvas" data-testid="atlas-canvas" />
      <footer>
        <span>Highlighted region:</span>
        <strong>{selectedRegion ?? 'None selected'}</strong>
      </footer>
    </section>
  );
};

export default AtlasViewer;
