import '@testing-library/jest-dom/vitest';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// @ts-expect-error jsdom globals extension
global.ResizeObserver = ResizeObserverMock;

Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  value: () => ({
    fillRect: () => {},
    clearRect: () => {},
    getImageData: () => ({ data: [] }),
    putImageData: () => {},
    createImageData: () => ({}),
    scale: () => {},
    translate: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    stroke: () => {},
    arc: () => {},
    fill: () => {},
    fillText: () => {},
    measureText: () => ({ width: 0 }),
    setTransform: () => {},
    save: () => {},
    restore: () => {}
  })
});

Object.defineProperty(HTMLCanvasElement.prototype, 'toDataURL', {
  value: () => 'data:image/png;base64,'
});
