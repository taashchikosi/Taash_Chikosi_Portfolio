import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Pin the tracing root to this app (a stray lockfile in $HOME otherwise confuses Next).
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
