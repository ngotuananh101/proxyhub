import '@testing-library/jest-dom'

// Node 25+ defines `globalThis.localStorage` as a getter that returns
// `undefined` unless the process was started with `--localstorage-file`. That
// getter shadows the one jsdom installs, so every `localStorage.getItem` in the
// app code throws. Define a plain in-memory implementation instead: it is
// per-worker, so test files never share state through a common file the way
// `--localstorage-file` would make them.
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.has(key) ? (store.get(key) as string) : null
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key: string) {
      store.delete(key)
    },
    setItem(key: string, value: string) {
      store.set(key, String(value))
    },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage,
  })
}
