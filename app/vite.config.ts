import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_PROXY_API_TARGET || "http://127.0.0.1:8000";
  const proxyPaths = [
    "/auth",
    "/categories",
    "/expenses",
    "/bills",
    "/reminders",
    "/dashboard",
    "/insights",
    "/health",
    "/metrics",
  ];

  return {
    define: {
      __FINMIND_VITE_API_URL__: JSON.stringify(env.VITE_API_URL || ""),
    },
    server: {
      host: "::",
      port: 5173,
      proxy: Object.fromEntries(
        proxyPaths.map((prefix) => [
          prefix,
          {
            target: proxyTarget,
            changeOrigin: true,
          },
        ]),
      ),
    },
    plugins: [react()].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});
