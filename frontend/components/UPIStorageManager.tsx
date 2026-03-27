"use client";
/**
 * UPIStorageManager – lightweight localStorage adapter for UPI analysis history.
 *
 * Root cause of the QuotaExceededError:
 *   The previous version stored the full `analysisData` object (10 000+ nodes/edges)
 *   inside every history entry, ballooning the key to several MB.  With even 2-3 entries
 *   the 5 MB localStorage budget is exhausted.
 *
 * Fix strategy:
 *   1. History entries store ONLY metadata — no graph data.
 *   2. Full analysis data is kept in sessionStorage (cleared on tab close, no quota concern
 *      for a single analysis blob) under a separate key.
 *   3. History is capped at MAX_ENTRIES; oldest entries are evicted first.
 *   4. Every write is wrapped in a quota-aware retry that prunes entries on QUOTA error.
 */

const UPI_HISTORY_KEY  = 'upi_analysis_history';   // metadata list  (localStorage)
const UPI_SESSION_PREFIX = 'upi_session_';          // full data blob (sessionStorage)
const MAX_ENTRIES = 5;

// ── helpers ───────────────────────────────────────────────────────────────────

/** Safe JSON parse; returns `fallback` on any error. */
const _safeParse = <T,>(raw: string | null, fallback: T): T => {
  if (!raw) return fallback;
  try { return JSON.parse(raw) as T; } catch { return fallback; }
};

/**
 * Write to localStorage with quota-aware retry.
 * If the first attempt throws QuotaExceededError, remove the oldest history entry
 * and try once more before giving up.
 */
const _safeSetItem = (key: string, value: string): boolean => {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch (err: unknown) {
      const isQuota =
        err instanceof DOMException &&
        (err.name === 'QuotaExceededError' ||
          err.name === 'NS_ERROR_DOM_QUOTA_REACHED');
      if (!isQuota) {
        console.error('[UPI_STORAGE] Unexpected localStorage error:', err);
        return false;
      }
      // Prune the oldest history entry and retry
      try {
        const raw = localStorage.getItem(UPI_HISTORY_KEY);
        const history: HistoryEntry[] = _safeParse(raw, []);
        if (history.length === 0) {
          console.error('[UPI_STORAGE] Quota exceeded but history is empty – cannot prune.');
          return false;
        }
        history.shift(); // remove oldest
        localStorage.setItem(UPI_HISTORY_KEY, JSON.stringify(history));
        console.warn(`[UPI_STORAGE] Quota exceeded – pruned oldest entry (attempt ${attempt + 1})`);
      } catch {
        return false;
      }
    }
  }
  return false;
};

// ── types ─────────────────────────────────────────────────────────────────────

interface HistoryEntry {
  fileName: string;
  timestamp: number;
  metadata: {
    nodeCount: number;
    edgeCount: number;
    riskScore: number;
    riskBand: string;
    source?: string;
  };
}

// ── public API ────────────────────────────────────────────────────────────────

export const UPIStorageManager = {
  /**
   * Save an analysis.
   *  - Metadata → localStorage history (capped at MAX_ENTRIES).
   *  - Full graph data → sessionStorage (survives page refresh, cleared on tab close).
   */
  saveAnalysis(fileName: string, analysisData: Record<string, unknown>): boolean {
    try {
      const timestamp = Date.now();

      const riskScore =
        (analysisData.risk as Record<string, unknown>)?.clusterRiskScore as number ||
        (analysisData.metadata as Record<string, unknown>)?.clusterRiskScore as number ||
        analysisData.riskScore as number || 0;

      const riskBand =
        (analysisData.risk as Record<string, unknown>)?.clusterRiskBand as string ||
        (analysisData.metadata as Record<string, unknown>)?.clusterRiskBand as string ||
        analysisData.riskBand as string || 'unknown';

      const graph = analysisData.graph as Record<string, unknown> | undefined;

      const entry: HistoryEntry = {
        fileName,
        timestamp,
        metadata: {
          nodeCount: Array.isArray(graph?.nodes) ? (graph.nodes as unknown[]).length : 0,
          edgeCount: Array.isArray(graph?.edges) ? (graph.edges as unknown[]).length : 0,
          riskScore: typeof riskScore === 'number' ? riskScore : 0,
          riskBand:  typeof riskBand  === 'string' ? riskBand  : 'unknown',
          source: 'local',
        },
      };

      // ── 1. Persist metadata to localStorage ──
      const history = UPIStorageManager.getHistory();
      const existingIdx = history.findIndex(h => h.fileName === fileName);
      if (existingIdx >= 0) {
        history[existingIdx] = entry;
      } else {
        history.push(entry);
        // Evict oldest entries beyond the cap
        while (history.length > MAX_ENTRIES) {
          const removed = history.shift();
          if (removed) {
            try { sessionStorage.removeItem(UPI_SESSION_PREFIX + removed.fileName); } catch { /* ignore */ }
          }
        }
      }

      const ok = _safeSetItem(UPI_HISTORY_KEY, JSON.stringify(history));

      // ── 2. Persist full data to sessionStorage ──
      try {
        sessionStorage.setItem(
          UPI_SESSION_PREFIX + fileName,
          JSON.stringify(analysisData)
        );
      } catch {
        // sessionStorage quota is per-origin but larger; log and continue
        console.warn('[UPI_STORAGE] sessionStorage write failed – full data not cached');
      }

      if (ok) {
        console.log('[UPI_STORAGE] Saved analysis:', fileName, entry.metadata);
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('upiAnalysisSaved', { detail: { fileName, timestamp } }));
        }
      }
      return ok;
    } catch (error) {
      console.error('[UPI_STORAGE] Error saving analysis:', error);
      return false;
    }
  },

  /**
   * Load full analysis data.
   * Checks sessionStorage first (fast), then falls back to reporting not found.
   */
  loadAnalysis(fileName: string): Record<string, unknown> | null {
    try {
      // Fast path: sessionStorage
      const session = sessionStorage.getItem(UPI_SESSION_PREFIX + fileName);
      if (session) {
        const data = _safeParse<Record<string, unknown>>(session, null as unknown as Record<string, unknown>);
        if (data) {
          console.log('[UPI_STORAGE] Loaded from session:', fileName);
          return data;
        }
      }
      console.warn('[UPI_STORAGE] Analysis not in session storage:', fileName);
      return null;
    } catch (error) {
      console.error('[UPI_STORAGE] Error loading analysis:', error);
      return null;
    }
  },

  /** Return the metadata-only history array from localStorage. */
  getHistory(): HistoryEntry[] {
    try {
      const raw = localStorage.getItem(UPI_HISTORY_KEY);
      const history = _safeParse<HistoryEntry[]>(raw, []);
      if (!Array.isArray(history)) {
        console.warn('[UPI_STORAGE] History is not an array, resetting');
        return [];
      }
      return history.filter(e => e && typeof e === 'object' && e.fileName && e.timestamp);
    } catch (error) {
      console.error('[UPI_STORAGE] Error getting history:', error);
      try { localStorage.removeItem(UPI_HISTORY_KEY); } catch { /* ignore */ }
      return [];
    }
  },

  /** Remove a specific analysis from both localStorage metadata and sessionStorage data. */
  deleteAnalysis(fileName: string): boolean {
    try {
      const history = UPIStorageManager.getHistory().filter(h => h.fileName !== fileName);
      _safeSetItem(UPI_HISTORY_KEY, JSON.stringify(history));
      try { sessionStorage.removeItem(UPI_SESSION_PREFIX + fileName); } catch { /* ignore */ }
      console.log('[UPI_STORAGE] Deleted analysis:', fileName);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('upiAnalysisDeleted', { detail: { fileName } }));
      }
      return true;
    } catch (error) {
      console.error('[UPI_STORAGE] Error deleting analysis:', error);
      return false;
    }
  },

  /** Wipe all history from localStorage and all session data. */
  clearAll(): boolean {
    try {
      // Clear all session storage keys matching our prefix
      try {
        Object.keys(sessionStorage)
          .filter(k => k.startsWith(UPI_SESSION_PREFIX))
          .forEach(k => sessionStorage.removeItem(k));
      } catch { /* ignore */ }
      localStorage.removeItem(UPI_HISTORY_KEY);
      console.log('[UPI_STORAGE] Cleared all analyses');
      return true;
    } catch (error) {
      console.error('[UPI_STORAGE] Error clearing storage:', error);
      return false;
    }
  },

  /** Approximate storage usage in KB for diagnostic display. */
  getStorageUsageKB(): number {
    try {
      const raw = localStorage.getItem(UPI_HISTORY_KEY) || '';
      return Math.round(raw.length * 2 / 1024);   // UTF-16 → bytes → KB
    } catch { return 0; }
  },
};
