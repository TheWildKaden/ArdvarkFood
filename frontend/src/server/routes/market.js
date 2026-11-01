import { getCompanyNews, getQuote } from "../services/market-data.js";
import { getRecentlyViewed, getWatchlist } from "../services/database.js";
import { logger } from "../../../packages/logger/index.js";

const indices = [
  { symbol: "^GSPC", label: "S&P 500" }, { symbol: "^IXIC", label: "NASDAQ" },
  { symbol: "^DJI", label: "Dow Jones" }, { symbol: "^RUT", label: "Russell 2000" },
];
const moverSymbols = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "AVGO", "META", "GOOGL"];

async function collectQuotes(items) {
  return Promise.all(items.map(async (item) => {
    try {
      return { ...await getQuote(item.symbol), ...(item.label ? { label: item.label } : {}) };
    } catch (error) {
      logger.warn("Market snapshot quote unavailable", { symbol: item.symbol, error: error.message });
      return { symbol: item.symbol, ...(item.label ? { label: item.label } : {}), error: error.message };
    }
  }));
}

export function registerMarketRoutes(app) {
  app.get("/api/market", async () => {
    const [marketIndices, movers, watchlistRows, recentRows, news] = await Promise.all([
      collectQuotes(indices), collectQuotes(moverSymbols.map((symbol) => ({ symbol }))),
      getWatchlist(), getRecentlyViewed(),
      getCompanyNews("SPY").catch((error) => {
        logger.warn("Market news unavailable", { error: error.message });
        return [];
      }),
    ]);
    const watchlist = await collectQuotes(watchlistRows);
    const recentlyViewed = await collectQuotes(recentRows);
    return {
      indices: marketIndices, movers, watchlist, recentlyViewed, news,
      marketStatus: marketIndices.some((quote) => quote.marketState === "Open") ? "Market open" : "Market closed",
      updatedAt: new Date().toISOString(),
    };
  });
}
