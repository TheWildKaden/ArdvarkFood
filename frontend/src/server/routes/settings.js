import { z } from "zod";
import { getSettings, updateSettings } from "../services/database.js";

const defaults = {
  theme: "dark", accent: "blue", compactMode: false, showNews: true,
  defaultRange: "1D", favoriteApps: ["home", "watchlist"],
};
const settingsSchema = z.object({
  theme: z.enum(["dark", "light", "system"]).optional(),
  accent: z.enum(["blue", "violet", "green", "amber"]).optional(),
  compactMode: z.boolean().optional(), showNews: z.boolean().optional(),
  defaultRange: z.enum(["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]).optional(),
  favoriteApps: z.array(z.string().min(1).max(40)).max(20).optional(),
});

export function registerSettingsRoutes(app) {
  app.get("/api/settings", async () => ({ settings: { ...defaults, ...getSettings() } }));
  app.patch("/api/settings", async (request, reply) => {
    const parsed = settingsSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Settings contain unsupported values." });
    return { settings: { ...defaults, ...updateSettings(parsed.data) } };
  });
}
