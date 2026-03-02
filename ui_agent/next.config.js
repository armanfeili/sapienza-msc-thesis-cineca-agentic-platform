/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable static export for simple deployment
  // Remove if you need SSR features
  output: 'standalone',
  
  // Disable React strict mode for development (optional)
  reactStrictMode: true,
  
  // Configure environment variables
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000',
  },
}

module.exports = nextConfig
