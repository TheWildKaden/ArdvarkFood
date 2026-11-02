import { z } from "zod";
import { getMetrics } from "../../../packages/monitoring/metrics.js";
import { listIncidents } from "../../../packages/logger/Incident.js";
import { getStatusSnapshot, listEvents, listLogs, listMonitors } from "../../../packages/logger/Status.js";

const limitSchema = z.coerce.number().int().min(1).max(200).default(100);
const incidentQuerySchema = z.object({
  status: z.enum(["active", "resolved"]).optional(),
  limit: limitSchema,
});
const logQuerySchema = z.object({
  level: z.enum(["debug", "info", "warn", "error", "fatal"]).optional(),
  limit: limitSchema,
});
const listQuerySchema = z.object({ limit: limitSchema });

export function registerLoggerRoutes(app) {
  app.get("/api/logger/status", async () => getStatusSnapshot());
  app.get("/api/logger/monitors", async () => ({ monitors: listMonitors() }));
  app.get("/api/logger/incidents", async (request, reply) => {
    const query = incidentQuerySchema.safeParse(request.query);
    if (!query.success) return reply.code(400).send({ error: "Invalid incident filter." });
    return { incidents: listIncidents(query.data) };
  });
  app.get("/api/logger/logs", async (request, reply) => {
    const query = logQuerySchema.safeParse(request.query);
    if (!query.success) return reply.code(400).send({ error: "Invalid log filter." });
    return { logs: listLogs(query.data) };
  });
  app.get("/api/logger/events", async (request, reply) => {
    const query = listQuerySchema.safeParse(request.query);
    if (!query.success) return reply.code(400).send({ error: "Invalid event filter." });
    return { events: listEvents(query.data.limit) };
  });
  app.get("/api/logger/metrics", async () => {
    const status = getStatusSnapshot();
    return {
      ...getMetrics(),
      overallStatus: status.overallStatus,
      componentCount: status.components.length,
      activeIncidentCount: status.activeIncidents.length,
      componentsByStatus: status.components.reduce((counts, component) => {
        counts[component.status] = (counts[component.status] ?? 0) + 1;
        return counts;
      }, {}),
    };
  });
}
