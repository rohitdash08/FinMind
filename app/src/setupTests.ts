import '@testing-library/jest-dom';
import 'whatwg-fetch';

// Silence React act warnings in tests output for cleaner logs
const originalError = console.error;
beforeAll(() => {
  jest.spyOn(console, 'error').mockImplementation((...args: any[]) => {
    const msg = args?.[0] ?? '';
    if (typeof msg === 'string' && msg.includes('Warning: An update to')) return;
    (originalError as any).call(console, ...args);
  });
});

afterAll(() => {
  (console.error as any).mockRestore?.();
});

// JSDOM polyfills for UI libs
if (typeof window.matchMedia !== 'function') {
  (window as any).matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(global as any).ResizeObserver = (global as any).ResizeObserver || RO;

// IntersectionObserver mock
;(global as any).IntersectionObserver = (global as any).IntersectionObserver || class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
