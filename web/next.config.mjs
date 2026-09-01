const nextConfig = {
  output: "standalone",
  experimental: {
    // Avoid spawning a detached `tsc --showConfig` process in restricted
    // container runtimes; Next uses the installed TypeScript compiler API.
    useTypeScriptCli: false,
  },
  async rewrites() {
    if (process.env.API_INTERNAL_URL) {
      return [
        {
          source: "/api/:path*",
          destination: `${process.env.API_INTERNAL_URL}/api/:path*`,
        },
      ];
    }
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
