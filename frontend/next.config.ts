import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // Dev convenience: proxy /api to the backend so CORS never bites.
    const base = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${base}/api/:path*` }];
  },
};

export default nextConfig;
