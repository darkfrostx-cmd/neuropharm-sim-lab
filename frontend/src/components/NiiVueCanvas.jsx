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

function normaliseVolume(volume) {
  if (!volume) {
    return null
  }
  const { url, name, format } = volume
  if (!url) {
    return null
  }
  const entry = {
    url,
    name: name || 'Overlay',
    colormap: 'red',
    opacity: 0.5,
  }
  if (format && format.toLowerCase() === 'gltf') {
    entry.isMesh = true
  }
  return entry
}

function deriveCoordinate(focusNode, overlay) {
  const firstOverlay = overlay?.coordinates?.[0]
  if (firstOverlay) {
    return {
      x: firstOverlay.x_mm ?? 0,
      y: firstOverlay.y_mm ?? 0,
      z: firstOverlay.z_mm ?? 0,
      source: 'overlay',
    }
  }
  const centres = focusNode?.attributes?.centers
  if (Array.isArray(centres) && centres.length) {
    const centre = centres[0]
    const toMm = (value) => {
      if (typeof value !== 'number') return 0
      return value / 1000
    }
    return {
      x: toMm(centre.x),
      y: toMm(centre.y),
      z: toMm(centre.z),
      source: 'node',
    }
  }
  return null
}

export default function NiiVueCanvas({ focusNode, overlay }) {
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

    const overlayVolumes = Array.isArray(overlay?.volumes)
      ? overlay.volumes.map(normaliseVolume).filter(Boolean)
      : []
    const meshEntries = overlayVolumes.filter((volume) => volume?.isMesh)
    const scalarVolumes = overlayVolumes.filter((volume) => !volume?.isMesh)
    const volumes = [DEFAULT_VOLUME, ...scalarVolumes]
    Promise.resolve(nv.loadVolumes(volumes)).catch((err) => {
      // eslint-disable-next-line no-console
      console.error('Failed to load NIfTI volumes', err)
    })
    if (meshEntries.length && typeof nv.addMesh === 'function') {
      meshEntries.forEach((mesh) => {
        nv.addMesh({ url: mesh.url, name: mesh.name || 'Mesh', opacity: 0.6 }).catch((err) => {
          // eslint-disable-next-line no-console
          console.error('Failed to load mesh overlay', err)
        })
      })
    }

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
  }, [overlay])

  useEffect(() => {
    if (NIIVUE_DISABLED) {
      return
    }

    const nv = nvRef.current
    if (!nv) {
      return
    }
    const coordinate = deriveCoordinate(focusNode, overlay)
    let mmX
    let mmY
    let mmZ
    if (coordinate) {
      mmX = coordinate.x ?? 0
      mmY = coordinate.y ?? 0
      mmZ = coordinate.z ?? 0
    } else if (focusNode?.id) {
      const hashed = hashToCoordinate(focusNode.id)
      mmX = hashed.x
      mmY = hashed.y
      mmZ = hashed.z
    } else {
      return
    }
    const dims = nv.voxDims?.[0] ?? { x: 1, y: 1, z: 1 }
    const clampedX = clamp(mmX, -dims.x * 90, dims.x * 90)
    const clampedY = clamp(mmY, -dims.y * 90, dims.y * 90)
    const clampedZ = clamp(mmZ, -dims.z * 90, dims.z * 90)
    if (typeof nv.setCrosshairLocation === 'function') {
      nv.setCrosshairLocation(clampedX, clampedY, clampedZ)
    }
  }, [focusNode, overlay])

  return <canvas ref={canvasRef} className="niivue-canvas" data-testid="niivue-canvas" />
}

NiiVueCanvas.propTypes = {
  focusNode: PropTypes.shape({
    id: PropTypes.string,
    attributes: PropTypes.object,
  }),
  overlay: PropTypes.shape({
    coordinates: PropTypes.arrayOf(
      PropTypes.shape({
        x_mm: PropTypes.number,
        y_mm: PropTypes.number,
        z_mm: PropTypes.number,
      }),
    ),
    volumes: PropTypes.arrayOf(
      PropTypes.shape({
        url: PropTypes.string,
        format: PropTypes.string,
      }),
    ),
  }),
}

NiiVueCanvas.defaultProps = {
  focusNode: null,
  overlay: null,
}

