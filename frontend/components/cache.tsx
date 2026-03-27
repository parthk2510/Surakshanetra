export class LRUCache {
  maxEntries: number;
  ttlMs: number;
  map: Map<string, { value: unknown; time: number }>;

  constructor({ maxEntries, ttlMs }: { maxEntries?: number; ttlMs?: number }) {
    this.maxEntries = Math.max(1, maxEntries || 100);
    this.ttlMs = Math.max(1000, ttlMs || 60000);
    this.map = new Map();
  }
  get(key) {
    const entry = this.map.get(key);
    if (!entry) return null;
    if (Date.now() - entry.time > this.ttlMs) {
      this.map.delete(key);
      return null;
    }
    this.map.delete(key);
    this.map.set(key, entry);
    return entry.value;
  }
  set(key, value) {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, { value, time: Date.now() });
    if (this.map.size > this.maxEntries) {
      const firstKey = this.map.keys().next().value;
      this.map.delete(firstKey);
    }
  }
}
