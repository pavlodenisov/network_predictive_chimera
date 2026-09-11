/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: false },
  // Emit a self-contained server bundle (Vercel doesn't need this, but Docker/Render do —
  // keeping both deploy paths open costs nothing).
  output: "standalone",
};
export default nextConfig;
