import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { registerApiRoutes } from "./routes/index.js";
import { logger } from "../../packages/logger/index.js";
import { registerComponent, pruneObservabilityData } from "../../packages/logger/Status.js";
import { initializeDatabase } from "./services/database.js";
import { recordRequest } from "../../packages/monitoring/metrics.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const app = Fastify({ logger: false, requestIdHeader: "x-request-id" });

initializeDatabase();
registerComponent({
  id: "spotify",
  name: "Spotify",
  category: "Core Services",
  description: "Playback credentials are private to this browser and are not reported to the server.",
  enabled: false,
});
registerComponent({
  id: "authentication",
  name: "Authentication",
  category: "Core Services",
  description: "This local workspace does not currently provide user authentication.",
  enabled: false,
});
app.addHook("onResponse", (request, reply, done) => {
  const duration = Number(reply.elapsedTime?.toFixed(2) ?? 0);
  recordRequest(reply.statusCode, duration);
  logger.request({ ...request, url: request.url.split("?")[0] }, reply, duration);
  done();
});
app.setErrorHandler((error, request, reply) => {
  const componentId = request.url.startsWith("/api/stocks") || request.url.startsWith("/api/search")
    ? "market-data-provider"
    : request.url.startsWith("/api/logger") ? "monitoring" : "node-server";
  logger.child({ componentId }).error(error, "Request failed", { requestId: request.id, statusCode: error.statusCode ?? 500, url: request.url.split("?")[0] });
  const statusCode = error.statusCode && (error.statusCode < 500 || error.statusCode === 502) ? error.statusCode : 500;
  reply.code(statusCode).send({ error: statusCode === 500 ? "Internal server error" : error.message, requestId: request.id });
});

registerApiRoutes(app);
pruneObservabilityData();
const pruneTimer = setInterval(pruneObservabilityData, 24 * 60 * 60_000);
pruneTimer.unref?.();
app.addHook("onClose", () => {
  clearInterval(pruneTimer);
  logger.stopMonitoring();
});
const builtClient = path.join(root, "dist");
if (fs.existsSync(builtClient)) {
  await app.register(fastifyStatic, { root: builtClient, prefix: "/" });
  app.setNotFoundHandler((request, reply) => {
    if (request.url.startsWith("/api/")) return reply.code(404).send({ error: "API route not found" });
    return reply.sendFile("index.html");
  });
}

const port = Number(process.env.PORT ?? 3000);
try {
  await app.listen({ port, host: process.env.HOST ?? "0.0.0.0" });
  logger.info("Server listening", { host: process.env.HOST ?? "0.0.0.0", port, environment: process.env.NODE_ENV ?? "production" });
  const localBase = `http://127.0.0.1:${port}`;
  logger.monitor("web-application", {
    name: "Web Application",
    category: "Core Services",
    description: "Production frontend is served by the local application server.",
    url: `${localBase}/`,
    interval: 30_000,
    timeout: 5_000,
  });
  logger.monitor("node-server", {
    name: "Node Server",
    category: "Core Services",
    description: "Fastify process health endpoint.",
    url: `${localBase}/api/health`,
    interval: 30_000,
    timeout: 5_000,
  });
  logger.monitor("stock-api", {
    name: "Stock API",
    category: "Core Services",
    description: "Stock quote, search, and chart routes are registered.",
    check: async () => ({ ok: app.hasRoute({ method: "GET", url: "/api/stocks/:symbol/quote" }) }),
    interval: 60_000,
    timeout: 2_000,
  });
  logger.monitor("search", {
    name: "Search",
    category: "Core Services",
    description: "Yahoo Finance symbol and company search endpoint.",
    url: "https://query1.finance.yahoo.com/v1/finance/search?q=SPY&quotesCount=1&newsCount=0",
    interval: 5 * 60_000,
    timeout: 8_000,
    failureThreshold: 2,
    slowThresholdMs: 5_000,
  });
  logger.monitor("sqlite", {
    name: "SQLite",
    category: "Infrastructure",
    description: "Local persistent database query check.",
    check: async () => ({ ok: initializeDatabase().prepare("SELECT 1").get()["1"] === 1 }),
    interval: 30_000,
    timeout: 2_000,
  });
  logger.monitor("monitoring", {
    name: "Monitoring",
    category: "Infrastructure",
    description: "Observability tables and health-check storage.",
    check: async () => ({ ok: initializeDatabase().prepare("SELECT COUNT(*) FROM checks").get() !== undefined }),
    interval: 60_000,
    timeout: 2_000,
  });
  logger.monitor("market-data-provider", {
    name: "Market Data Provider",
    category: "Infrastructure",
    description: "Yahoo Finance public market-data endpoint; availability may be limited or rate-limited.",
    url: "https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d",
    interval: 5 * 60_000,
    timeout: 8_000,
    failureThreshold: 2,
    slowThresholdMs: 5_000,
  });
} catch (error) {
  logger.fatal(error, "Unable to start server");
  process.exitCode = 1;
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, async () => {
    logger.info("Server shutting down", { signal });
    await app.close();
    process.exit(0);
  });
}
