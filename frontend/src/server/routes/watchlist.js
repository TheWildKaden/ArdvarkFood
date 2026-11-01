import { z } from "zod";
import { addToWatchlist, getWatchlist, removeFromWatchlist, reorderWatchlist } from "../services/database.js";
import { getQuote } from "../services/market-data.js";

const symbolSchema = z.string().trim().min(1).max(15).regex(/^[A-Za-z0-9^=.-]+$/).transform((value) => value.toUpperCase());

export function registerWatchlistRoutes(app) {
  app.get("/api/watchlist", async () => ({
    watchlist: await Promise.all(getWatchlist().map(async ({ symbol, position, addedAt }) => {
      try { return { ...await getQuote(symbol), position, addedAt }; }
      catch (error) { return { symbol, position, addedAt, error: error.message, price: null }; }
    })),
  }));
  app.post("/api/watchlist", async (request, reply) => {
    const parsed = z.object({ symbol: symbolSchema }).safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Provide a valid ticker symbol." });
    const quote = await getQuote(parsed.data.symbol);
    const watchlist = addToWatchlist(parsed.data.symbol);
    return reply.code(201).send({ watchlist, added: quote });
  });
  app.delete("/api/watchlist/:symbol", async (request, reply) => {
    const parsed = symbolSchema.safeParse(request.params.symbol);
    if (!parsed.success) return reply.code(400).send({ error: "Invalid ticker symbol." });
    return { watchlist: removeFromWatchlist(parsed.data) };
  });
  app.put("/api/watchlist/reorder", async (request, reply) => {
    const parsed = z.object({ symbols: z.array(symbolSchema).max(200) }).safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Provide an ordered list of ticker symbols." });
    const existing = getWatchlist().map(({ symbol }) => symbol).sort();
    const requested = [...parsed.data.symbols].sort();
    if (existing.length !== requested.length || existing.some((symbol, index) => symbol !== requested[index])) {
      return reply.code(400).send({ error: "Reordering must include every watchlist symbol exactly once." });
    }
    return { watchlist: reorderWatchlist(parsed.data.symbols) };
  });
}
