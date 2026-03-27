import type { NextConfig } from "next";
import path from "path";

// output:'standalone' is needed for the Docker image (self-hosted / docker-compose).
// Vercel manages its own output pipeline, so we skip it there to avoid conflicts.
// Set NEXT_BUILD_STANDALONE=true in the Docker build step (see backend/dockerfile).
const isDockerBuild = process.env.NEXT_BUILD_STANDALONE === "true";

const nextConfig: NextConfig = {
  ...(isDockerBuild ? { output: "standalone" } : {}),
  typescript: {
    ignoreBuildErrors: true,
  },
  // Pin Turbopack's root to this directory so it doesn't crawl up to
  // C:\Users\kpart\package.json and mis-resolve node_modules.
  turbopack: {
    root: path.resolve(__dirname),
  },
  experimental: {
    proxyClientMaxBodySize: 52428800,
    serverActions: {
      bodySizeLimit: '50mb',
    },
  },
  // Increase server-side proxy timeout so long-running UPI analysis
  // does not cause ECONNRESET when running `npm start` locally.
  serverExternalPackages: [],
  httpAgentOptions: { keepAlive: true },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
