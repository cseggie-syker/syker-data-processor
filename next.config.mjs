/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (process.env.NEXT_PUBLIC_API_BASE_URL) {
      return [];
    }

    if (process.env.NODE_ENV === "development") {
      return [
        {
          source: "/api/process",
          destination: "http://127.0.0.1:8000/process",
        },
      ];
    }

    return [];
  },
};

export default nextConfig;


