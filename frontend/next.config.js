/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // Environment variables available at runtime
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003',
  },

  // Disable image optimization for Cloud Run (uses external URLs)
  images: {
    unoptimized: true,
  },
}

module.exports = nextConfig
