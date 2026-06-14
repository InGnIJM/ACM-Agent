import "@testing-library/jest-dom";

// jsdom does not implement ResizeObserver, which Recharts ResponsiveContainer needs.
// The mock must fire the callback so ResponsiveContainer sets width/height and renders children.
global.ResizeObserver = class ResizeObserver {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    // Trigger the callback immediately with a plausible content rect so
    // Recharts ResponsiveContainer will render its SVG children.
    this.callback(
      [{ contentRect: { width: 400, height: 300, x: 0, y: 0, top: 0, right: 400, bottom: 300, left: 0 }, target, borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
};
