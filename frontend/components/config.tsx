"use client";
export const config = {
  port: Number.parseInt(process.env.UPI_BACKEND_PORT || process.env.PORT || '6001', 10),
  neo4j: {
    uri: process.env.NEO4J_URI || '',
    user: process.env.NEO4J_USER || '',
    password: process.env.NEO4J_PASSWORD || ''
  },
  cache: {
    maxEntries: 200,
    ttlMs: 120000
  },
  limits: {
    maxTxLimit: 1000,
    maxTimelineEvents: 200,
    maxCentralityNodes: 200,
    maxClosenessNodes: 500
  },
  rules: {
    fanIn: { unique: 8, count: 15, ratio: 2 },
    fanOut: { unique: 8, count: 15, ratio: 2 },
    circular: { minCycleSize: 2 },
    rapidInOut: { maxMinutes: 120, minMatches: 3, minRatio: 0.5 },
    structuring: { threshold: 10000, windowPct: 0.1, minCount: 5, repeatCount: 6, varianceRatio: 0.1 },
    dormantSpike: { dormantDays: 30, burstHours: 24, burstCount: 5 },
    passthrough: { ratioLow: 0.8, ratioHigh: 1.2, maxHoldMinutes: 180, minCount: 3 }
  },
  weights: {
    fanIn: 15,
    fanOut: 15,
    circular: 15,
    rapidInOut: 15,
    structuring: 10,
    dormantSpike: 10,
    passthrough: 20
  }
};
