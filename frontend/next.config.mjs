const isDevelopment = process.env.NODE_ENV === "development";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      `connect-src 'self'${isDevelopment ? " http://localhost:8000 http://127.0.0.1:8000" : ""}`,
      "font-src 'self'",
      "object-src 'none'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "form-action 'self'",
    ].join("; "),
  },
];

// Development only: proxy the API through the dev server so the browser stays
// same-origin (e.g. OMNIOPS_DEV_API_PROXY=http://localhost). Never used in builds.
const devApiProxy = isDevelopment ? process.env.OMNIOPS_DEV_API_PROXY : undefined;

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
  async rewrites() {
    return devApiProxy ? [{ source: "/api/v1/:path*", destination: `${devApiProxy}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
