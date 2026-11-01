import { z } from "zod";
import { logger } from "../../../packages/logger/index.js";

const yahooBase = "https://query1.finance.yahoo.com";
const nasdaqBase = "https://api.nasdaq.com/api";
const nasdaqIndices = { "^IXIC": "COMP" };
const cache = new Map();
const inflight = new Map();
const rangeConfig = {
  "1D": ["1d", "5m"], "5D": ["5d", "15m"], "1M": ["1mo", "1d"], "6M": ["6mo", "1d"],
  YTD: ["ytd", "1d"], "1Y": ["1y", "1d"], "5Y": ["5y", "1wk"], MAX: ["max", "1mo"],
};
const symbolSchema = z.string().trim().min(1).max(15).regex(/^[A-Za-z0-9^=.-]+$/);

class MarketDataError extends Error {
  constructor(message, cause) {
    super(message, { cause });
    this.name = "MarketDataError";
    this.statusCode = 502;
  }
}

function validateSymbol(input) {
  return symbolSchema.parse(input).toUpperCase();
}

async function fetchJson(url) {
  let response;
  try {
    response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        Accept: "application/json, text/plain, */*",
        Origin: "https://www.nasdaq.com",
        Referer: "https://www.nasdaq.com/",
      },
      signal: AbortSignal.timeout(12_000),
    });
  } catch (error) {
    throw new MarketDataError("Unable to reach the market data provider.", error);
  }
  if (!response.ok) throw new MarketDataError(`Market data provider returned HTTP ${response.status}.`);
  try {
    const payload = await response.json();
    if (payload?.status?.rCode && payload.status.rCode !== 200) {
      throw new MarketDataError(payload.status.bCodeMessage?.[0]?.errorMessage ?? "The provider rejected the request.");
    }
    return payload;
  } catch (error) {
    if (error instanceof MarketDataError) throw error;
    throw new MarketDataError("Market data provider returned an invalid response.", error);
  }
}

async function fetchYahooJson(url) {
  try {
    return await fetchJson(url);
  } catch (firstError) {
    const fallback = new URL(url);
    if (!fallback.hostname.startsWith("query1.")) throw firstError;
    fallback.hostname = fallback.hostname.replace("query1.", "query2.");
    try {
      return await fetchJson(fallback);
    } catch (fallbackError) {
      throw new MarketDataError(
        `Market data providers are unavailable (Yahoo Finance: ${firstError.message}; fallback: ${fallbackError.message}).`,
        fallbackError,
      );
    }
  }
}

function parseNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const parsed = Number(value.replace(/[$,%\s,]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function getNasdaqAsset(symbol) {
  const mapped = nasdaqIndices[symbol];
  return { symbol: mapped ?? symbol, assetClass: mapped ? "index" : "stocks" };
}

function asIsoTimestamp(value) {
  if (!value) return new Date().toISOString();
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : new Date().toISOString();
}

async function getNasdaqQuote(symbol) {
  const asset = getNasdaqAsset(symbol);
  const url = new URL(`${nasdaqBase}/quote/${encodeURIComponent(asset.symbol)}/info`);
  url.searchParams.set("assetclass", asset.assetClass);
  const payload = await fetchJson(url);
  const data = payload?.data;
  const primary = data?.primaryData;
  const price = parseNumber(primary?.lastSalePrice);
  if (!data || price === null) throw new MarketDataError(`Nasdaq returned no quote for ${symbol}.`);
  const change = parseNumber(primary.netChange);
  const previousClose = change === null ? null : price - change;
  const weekRange = data.keyStats?.fiftyTwoWeekHighLow?.value?.split(" - ").map(parseNumber) ?? [];
  return {
    symbol,
    name: data.companyName ?? symbol,
    exchange: data.exchange ?? "",
    currency: primary.currency || "USD",
    price,
    previousClose,
    change,
    changePercent: parseNumber(primary.percentageChange),
    marketState: data.marketStatus ?? "Delayed",
    volume: parseNumber(primary.volume),
    marketCap: null,
    peRatio: null,
    fiftyTwoWeekLow: weekRange[0] ?? null,
    fiftyTwoWeekHigh: weekRange[1] ?? null,
    timestamp: asIsoTimestamp(primary.lastTradeTimestamp),
    source: "Nasdaq",
  };
}

async function getNasdaqSummary(symbol) {
  const asset = getNasdaqAsset(symbol);
  const url = new URL(`${nasdaqBase}/quote/${encodeURIComponent(asset.symbol)}/summary`);
  url.searchParams.set("assetclass", asset.assetClass);
  return (await fetchJson(url)).data?.summaryData ?? null;
}

async function cached(key, load, ttl = 30_000) {
  const found = cache.get(key);
  if (found && Date.now() - found.time < ttl) return found.value;
  if (inflight.has(key)) return inflight.get(key);
  const pending = Promise.resolve().then(load).then((value) => {
    if (cache.size > 1000) {
      const now = Date.now();
      for (const [entryKey, entry] of cache) {
        if (now - entry.time > 10 * 60_000) cache.delete(entryKey);
      }
      while (cache.size >= 1000) cache.delete(cache.keys().next().value);
    }
    cache.set(key, { value, time: Date.now() });
    return value;
  }).finally(() => inflight.delete(key));
  inflight.set(key, pending);
  return pending;
}

function quoteFromChart(symbol, payload) {
  const result = payload?.chart?.result?.[0];
  if (!result) throw new Error(payload?.chart?.error?.description ?? `No market data found for ${symbol}`);
  const meta = result.meta;
  const quote = result.indicators?.quote?.[0] ?? {};
  const closes = (quote.close ?? []).filter(Number.isFinite);
  const price = meta.regularMarketPrice ?? closes.at(-1) ?? null;
  const previousClose = meta.chartPreviousClose ?? meta.previousClose ?? null;
  const change = price !== null && previousClose !== null ? price - previousClose : null;
  const regular = meta.currentTradingPeriod?.regular;
  const now = Date.now() / 1000;
  return {
    symbol, name: meta.longName ?? meta.shortName ?? symbol,
    exchange: meta.fullExchangeName ?? meta.exchangeName ?? "", currency: meta.currency ?? "USD",
    price, previousClose, change, changePercent: change !== null && previousClose ? (change / previousClose) * 100 : null,
    marketState: regular ? (now >= regular.start && now <= regular.end ? "Open" : "Closed") : "Delayed",
    volume: meta.regularMarketVolume ?? quote.volume?.filter(Number.isFinite).at(-1) ?? null,
    marketCap: meta.marketCap ?? null, peRatio: meta.trailingPE ?? meta.forwardPE ?? null,
    fiftyTwoWeekHigh: meta.fiftyTwoWeekHigh ?? null, fiftyTwoWeekLow: meta.fiftyTwoWeekLow ?? null,
    timestamp: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : new Date().toISOString(),
  };
}

export async function getQuote(input) {
  const symbol = validateSymbol(input);
  return cached(`quote:${symbol}`, async () => {
    try {
      return await getNasdaqQuote(symbol);
    } catch (nasdaqError) {
      logger.warn("Nasdaq quote unavailable; trying Yahoo Finance", { symbol, error: nasdaqError.message });
      const url = new URL(`${yahooBase}/v8/finance/chart/${encodeURIComponent(symbol)}`);
      url.searchParams.set("range", "1d");
      url.searchParams.set("interval", "5m");
      try {
        return { ...quoteFromChart(symbol, await fetchYahooJson(url)), source: "Yahoo Finance" };
      } catch (yahooError) {
        throw new MarketDataError(
          `Unable to load a quote for ${symbol} (Nasdaq: ${nasdaqError.message}; Yahoo Finance: ${yahooError.message}).`,
          yahooError,
        );
      }
    }
  });
}

export async function searchStocks(query) {
  const normalized = z.string().trim().min(1).max(60).parse(query);
  return cached(`search:${normalized.toLowerCase()}`, async () => {
    const url = new URL(`${yahooBase}/v1/finance/search`);
    url.searchParams.set("q", normalized);
    url.searchParams.set("quotesCount", "12");
    url.searchParams.set("newsCount", "0");
    let payload;
    try {
      payload = await fetchYahooJson(url);
    } catch (error) {
      if (/^[A-Za-z0-9.^=-]{1,15}$/.test(normalized)) {
        try {
          return [await getQuote(normalized)];
        } catch (quoteError) {
          throw new MarketDataError(`Stock search is unavailable: ${error.message}; direct ticker lookup also failed: ${quoteError.message}.`, quoteError);
        }
      }
      throw error;
    }
    const quotes = (payload.quotes ?? []).filter((quote) => ["EQUITY", "ETF", "INDEX"].includes(quote.quoteType) && quote.symbol);
    return Promise.all(quotes.slice(0, 8).map(async (quote) => {
      try {
        const current = await getQuote(quote.symbol);
        return { ...current, name: quote.longname ?? quote.shortname ?? current.name, exchange: quote.exchDisp ?? current.exchange };
      } catch (error) {
        logger.warn("Search result quote unavailable", { symbol: quote.symbol, error: error.message });
        return { symbol: quote.symbol, name: quote.longname ?? quote.shortname ?? quote.symbol, exchange: quote.exchDisp ?? "", price: null, change: null, changePercent: null, error: error.message };
      }
    }));
  }, 20_000);
}

async function getYahooChart(symbol, range, period, interval) {
  const url = new URL(`${yahooBase}/v8/finance/chart/${encodeURIComponent(symbol)}`);
  url.searchParams.set("range", period);
  url.searchParams.set("interval", interval);
  url.searchParams.set("events", "div,splits");
  const payload = await fetchYahooJson(url);
  const result = payload?.chart?.result?.[0];
  if (!result) throw new MarketDataError(payload?.chart?.error?.description ?? `No chart data found for ${symbol}.`);
  return makeChart(symbol, range, result.timestamp ?? [], result.indicators?.quote?.[0] ?? {}, result.indicators?.adjclose?.[0]?.adjclose ?? [], quoteFromChart(symbol, payload), result.meta.currency ?? "USD");
}

function makeChart(symbol, range, timestamps, quoteData, adjustedCloses, quote, currency = "USD") {
  const points = timestamps.flatMap((time, index) => {
    const value = quoteData.close?.[index] ?? adjustedCloses[index];
    return Number.isFinite(value) ? [{ time, value }] : [];
  });
  const candles = timestamps.flatMap((time, index) => {
    const candle = { time, open: quoteData.open?.[index], high: quoteData.high?.[index], low: quoteData.low?.[index], close: quoteData.close?.[index] };
    return Object.values(candle).slice(1).every(Number.isFinite) ? [candle] : [];
  });
  const volume = timestamps.flatMap((time, index) => {
    const value = quoteData.volume?.[index];
    const close = quoteData.close?.[index];
    const previous = quoteData.close?.[index - 1];
    return Number.isFinite(value) ? [{
      time,
      value,
      color: Number.isFinite(previous) && Number.isFinite(close) && close >= previous
        ? "rgba(101, 200, 155, 0.38)"
        : "rgba(226, 120, 120, 0.38)",
    }] : [];
  });
  if (!points.length) throw new MarketDataError(`No chart data found for ${symbol} in the selected range.`);
  return { symbol, range, points, candles, volume, quote, currency };
}

async function getNasdaqChart(symbol, range) {
  const asset = getNasdaqAsset(symbol);
  const now = new Date();
  const from = new Date(now);
  const days = { "1D": 1, "5D": 10, "1M": 45, "6M": 190, YTD: 370, "1Y": 370, "5Y": 1830, MAX: 7300 };
  if (range === "YTD") {
    from.setUTCMonth(0, 1);
    from.setUTCHours(0, 0, 0, 0);
  }
  else from.setUTCDate(from.getUTCDate() - days[range]);
  const fromDate = from.toISOString().slice(0, 10);
  const url = new URL(`${nasdaqBase}/quote/${encodeURIComponent(asset.symbol)}/historical`);
  url.searchParams.set("assetclass", asset.assetClass);
  url.searchParams.set("fromdate", fromDate);
  url.searchParams.set("todate", now.toISOString().slice(0, 10));
  url.searchParams.set("limit", "5000");
  const payload = await fetchJson(url);
  const rows = payload?.data?.tradesTable?.rows ?? [];
  if (!rows.length) throw new MarketDataError(`Nasdaq returned no chart history for ${symbol}.`);
  const parsedRows = rows.flatMap((row) => {
    const date = row.date ? new Date(`${row.date} UTC`) : null;
    const time = date && Number.isFinite(date.getTime()) ? Math.floor(date.getTime() / 1000) : null;
    const candle = {
      time,
      open: parseNumber(row.open),
      high: parseNumber(row.high),
      low: parseNumber(row.low),
      close: parseNumber(row.close),
      volume: parseNumber(row.volume),
    };
    return time !== null && Number.isFinite(candle.close) ? [candle] : [];
  }).reverse();
  const quoteData = {
    open: parsedRows.map((row) => row.open),
    high: parsedRows.map((row) => row.high),
    low: parsedRows.map((row) => row.low),
    close: parsedRows.map((row) => row.close),
    volume: parsedRows.map((row) => row.volume),
  };
  return makeChart(symbol, range, parsedRows.map((row) => row.time), quoteData, [], await getQuote(symbol));
}

export async function getChart(input, rangeInput = "1D") {
  const symbol = validateSymbol(input);
  const range = z.enum(["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]).parse(rangeInput);
  return cached(`chart:${symbol}:${range}`, async () => {
    if (range === "1D" || range === "5D") {
      const [period, interval] = rangeConfig[range];
      try {
        return await getYahooChart(symbol, range, period, interval);
      } catch (error) {
        logger.warn("Intraday Yahoo chart unavailable; trying Nasdaq history", { symbol, range, error: error.message });
        return getNasdaqChart(symbol, range);
      }
    }
    try {
      return await getNasdaqChart(symbol, range);
    } catch (error) {
      logger.warn("Nasdaq historical chart unavailable; trying Yahoo Finance", { symbol, range, error: error.message });
      const [period, interval] = rangeConfig[range];
      return getYahooChart(symbol, range, period, interval);
    }
  }, 60_000);
}

export async function getCompanyNews(input) {
  const symbol = validateSymbol(input);
  return cached(`news:${symbol}`, async () => {
    const url = new URL(`${yahooBase}/v1/finance/search`);
    url.searchParams.set("q", symbol);
    url.searchParams.set("quotesCount", "0");
    url.searchParams.set("newsCount", "8");
    const payload = await fetchYahooJson(url);
    return (payload.news ?? []).map((item) => ({
      title: item.title, publisher: item.publisher, url: item.link,
      publishedAt: item.providerPublishTime ? new Date(item.providerPublishTime * 1000).toISOString() : null,
      thumbnail: item.thumbnail?.resolutions?.[0]?.url ?? null,
    }));
  }, 120_000);
}

export async function getStockDetails(input) {
  const symbol = validateSymbol(input);
  const [quote, chart, news, summary] = await Promise.all([
    getQuote(symbol),
    getChart(symbol, "1Y"),
    getCompanyNews(symbol).catch((error) => {
      logger.warn("Company news unavailable", { symbol, error: error.message });
      return [];
    }),
    getNasdaqSummary(symbol).catch((error) => {
      logger.warn("Company market summary unavailable", { symbol, error: error.message });
      return null;
    }),
  ]);
  const marketCap = parseNumber(summary?.MarketCap?.value);
  const previousClose = parseNumber(summary?.PreviousClose?.value) ?? quote.previousClose;
  return {
    ...quote,
    marketCap: marketCap ?? quote.marketCap,
    previousClose,
    chart,
    news,
  };
}
