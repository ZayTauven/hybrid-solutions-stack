/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The core ships TypeScript source rather than a build step, so Next has to
  // compile it like first-party code. Every skin needs this line.
  transpilePackages: ['@hybrid/offline-core'],
};

export default nextConfig;
