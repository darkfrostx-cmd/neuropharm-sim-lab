export function hashToCoordinate(key) {
  if (!key) {
    return { x: 0, y: 0, z: 0 }
  }
  let hash = 0
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  }
  const normalise = (value) => (value % 180) - 90
  return {
    x: normalise(hash),
    y: normalise(hash >> 3),
    z: normalise(hash >> 5),
  }
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

