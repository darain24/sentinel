/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["react-leaflet", "leaflet"],
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: "/api/index.py",
      },
    ];
  },
};

export default nextConfig;
