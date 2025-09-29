import type { NextConfig } from "next";

/**
 * Next.js configuration
 * - output: "export" to allow static export for the UI shell.
 * - rewrites: if NEXT_PUBLIC_BACKEND_URL is present, proxy /api/ask to the backend
 *   at ${NEXT_PUBLIC_BACKEND_URL}/api/ask. This avoids CORS issues during local/dev,
 *   keeps a clean frontend URL, and allows the UI to stream directly from the backend.
 */
const nextConfig: NextConfig = {
  output: "export",
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_BACKEND_URL;
    if (!backend) return [];
    return [
      {
        source: "/api/ask",
        destination: `${backend.replace(/\/+$/, "")}/api/ask`,
      },
    ];
  },
};

export default nextConfig;
