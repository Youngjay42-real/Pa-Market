/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "media-cdn.tripadvisor.com",
        pathname: "/media/**",
      },
    ],
  },
  // StandProof chatbot proxy (docs/CHATBOT_CONTRACT.md §9):
  // when FLASK_API_URL is set, /api/v1/* is forwarded to the Flask backend.
  // Both the workspace adapter and Market Assistant can then call this
  // same-origin path in local and hosted deployments.
  async rewrites() {
    if (!process.env.FLASK_API_URL) return [];
    const flask = String(process.env.FLASK_API_URL).replace(/\/$/, "");
    return [
      {
        source: "/api/v1/:path*",
        destination: `${flask}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
