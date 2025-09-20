import { useEffect, useRef } from 'react'
import PropTypes from 'prop-types'
import { Niivue } from '@niivue/niivue'
import { hashToCoordinate, clamp } from '../utils/spatial'
import './NiiVueCanvas.css'

const DEFAULT_VOLUME = {
  url: 'https://niivue.github.io/niivue/images/mni152.nii.gz',
  name: 'MNI152',
}

const NIIVUE_DISABLED = import.meta.env.VITE_DISABLE_NIIVUE === 'true'

export default function NiiVueCanvas({ focusKey, overlays }) {
  const canvasRef = useRef(null)
  const nvRef = useRef(null)

  useEffect(() => {
    if (NIIVUE_DISABLED) {
      return () => {}
    }

    const canvas = canvasRef.current
    if (!canvas) {
      return () => {}
    }
    let nv
    try {
      nv = new Niivue({
        loadingText: 'Loading atlas…',
        show3Dcrosshair: true,
        show3Dcursor: true,
      })
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Failed to initialise NiiVue', err)
      return () => {}
    }
    nvRef.current = nv
    nv.attachToCanvas(canvas)
    nv.setSliceType(nv.sliceTypeAxial)
    nv.opts.isColorbar = true

    const volumes = [DEFAULT_VOLUME, ...(overlays || [])].filter((volume) => volume && volume.url)
    Promise.resolve(nv.loadVolumes(volumes)).catch((err) => {
      // eslint-disable-next-line no-console
      console.error('Failed to load NIfTI volumes', err)
    })

    return () => {
      nvRef.current = null
      if (nv && typeof nv.destroy === 'function') {
        nv.destroy()
      } else if (nv?.gl?.canvas) {
        try {
          nv.gl.canvas.width = 0
          nv.gl.canvas.height = 0
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error('Failed to tear down NiiVue canvas', err)
        }
      }
    }
  }, [overlays])

  useEffect(() => {
    if (NIIVUE_DISABLED) {
      return
    }

    const nv = nvRef.current
    if (!nv || !focusKey) {
      return
    }
    const { x, y, z } = hashToCoordinate(focusKey)
    const dims = nv.voxDims?.[0] ?? { x: 1, y: 1, z: 1 }
    const mmX = clamp(x, -dims.x * 90, dims.x * 90)
    const mmY = clamp(y, -dims.y * 90, dims.y * 90)
    const mmZ = clamp(z, -dims.z * 90, dims.z * 90)
    if (typeof nv.setCrosshairLocation === 'function') {
      nv.setCrosshairLocation(mmX, mmY, mmZ)
    }
  }, [focusKey])

  return <canvas ref={canvasRef} className="niivue-canvas" data-testid="niivue-canvas" />
}

NiiVueCanvas.propTypes = {
  focusKey: PropTypes.string,
  overlays: PropTypes.arrayOf(
    PropTypes.shape({
      url: PropTypes.string.isRequired,
      name: PropTypes.string,
    }),
  ),
}

NiiVueCanvas.defaultProps = {
  focusKey: null,
  overlays: undefined,
}

