import { registerMarketRoutes } from "./market.js";
import { registerStockRoutes } from "./stocks.js";
import { registerWatchlistRoutes } from "./watchlist.js";
import { registerSettingsRoutes } from "./settings.js";
import { registerLoggerRoutes } from "./logger.js";
import { getMetrics } from "../../../packages/monitoring/metrics.js";

export function registerApiRoutes(app) {
  app.get("/api/health", async () => ({
    status: "ok",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    version: process.env.npm_package_version ?? "1.0.0",
  }));
  app.get("/api/metrics", async () => getMetrics());
  registerMarketRoutes(app);
  registerStockRoutes(app);
  registerWatchlistRoutes(app);
  registerSettingsRoutes(app);
  registerLoggerRoutes(app);
}
