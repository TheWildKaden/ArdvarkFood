import { z } from "zod";
import { addRecentlyViewed } from "../services/database.js";
import { getChart, getCompanyNews, getQuote, getStockDetails, searchStocks } from "../services/market-data.js";

const symbolSchema = z.string().trim().min(1).max(15).regex(/^[A-Za-z0-9^=.-]+$/);
const searchSchema = z.object({ q: z.string().trim().min(1).max(60) });
const chartSchema = z.object({ range: z.enum(["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]).default("1D") });

export function registerStockRoutes(app) {
  app.get("/api/search", async (request, reply) => {
    const parsed = searchSchema.safeParse(request.query);
    if (!parsed.success) return reply.code(400).send({ error: "Enter a ticker or company name." });
    return { results: await searchStocks(parsed.data.q) };
  });
  app.get("/api/stocks/:symbol", async (request, reply) => {
    const params = symbolSchema.safeParse(request.params.symbol);
    if (!params.success) return reply.code(400).send({ error: "Invalid ticker symbol." });
    const symbol = params.data.toUpperCase();
    const stock = await getStockDetails(symbol);
    addRecentlyViewed(symbol);
    return stock;
  });
  app.get("/api/stocks/:symbol/quote", async (request, reply) => {
    const params = symbolSchema.safeParse(request.params.symbol);
    if (!params.success) return reply.code(400).send({ error: "Invalid ticker symbol." });
    return getQuote(params.data);
  });
  app.get("/api/stocks/:symbol/chart", async (request, reply) => {
    const params = symbolSchema.safeParse(request.params.symbol);
    const query = chartSchema.safeParse(request.query);
    if (!params.success || !query.success) return reply.code(400).send({ error: "Invalid symbol or chart range." });
    return getChart(params.data, query.data.range);
  });
  app.get("/api/stocks/:symbol/news", async (request, reply) => {
    const params = symbolSchema.safeParse(request.params.symbol);
    if (!params.success) return reply.code(400).send({ error: "Invalid ticker symbol." });
    return { news: await getCompanyNews(params.data) };
  });
}
