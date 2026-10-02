import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  typedRoutes: false,
  outputFileTracingRoot: __dirname,
  webpack: (config) => {
    config.resolve.alias['@'] = resolve(__dirname, 'src');
    return config;
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`
      }
    ];
  }
};

export default nextConfig;