/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: false },
  // Emit a self-contained server bundle for the Docker/Render image.
  output: "standalone",
};
export default nextConfig;
