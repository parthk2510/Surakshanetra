/**
 * Centralised z-index layer system for ChainBreak UI.
 *
 * Rule: every positioned element that participates in stacking MUST pull
 * its z-index from this file.  Never use a magic number.
 *
 * Layer order (low → high):
 *   graph canvas         0
 *   graph controls      10
 *   graph legend        12
 *   sidebar             20
 *   header / nav        30
 *   sticky sub-headers  30
 *   modal backdrops     40
 *   modals / panels     45
 *   node detail panel   45
 *   decision panel      46   ← must clear node-detail
 *   settings panel      47   ← must clear both above
 *   tooltips            50
 *   toasts             100
 */

export const Z = {
  /** D3 / canvas graph surface */
  GRAPH_CANVAS: 0,
  /** In-graph controls (freeze, fit-view) */
  GRAPH_CONTROLS: 10,
  /** Risk legend overlay */
  GRAPH_LEGEND: 12,
  /** Left sidebar */
  SIDEBAR: 20,
  /** Top application header */
  HEADER: 30,
  /** Sticky sub-headers (dashboard inner header) */
  STICKY_SUBHEADER: 30,
  /** Semi-transparent modal/panel backdrop */
  MODAL_BACKDROP: 40,
  /** Generic modals, flyouts, floating panels */
  MODAL: 45,
  /** Node detail intelligence panel */
  NODE_DETAIL: 45,
  /** RGCN Decision Engine panel (sits next to node detail) */
  DECISION_PANEL: 46,
  /** Global Settings panel (slides from right) */
  SETTINGS_PANEL: 47,
  /** Hover / focus tooltips */
  TOOLTIP: 50,
  /** React-hot-toast notifications */
  TOAST: 100,
} as const;

export type ZLayer = typeof Z[keyof typeof Z];
