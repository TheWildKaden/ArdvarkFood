import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowUpRight, ExternalLink, Plus, Star } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../services/api.js";
import { useAppStore } from "../state/store.js";
import { Change, EmptyState, Loading, SectionHeading } from "../components/ui.jsx";
import StockChart from "../components/StockChart.jsx";
import { formatCurrency, formatNumber, formatTimeAgo } from "../services/format.js";

export default function StockPage() {
  const { symbol = "" } = useParams();
  const navigate = useNavigate();
  const watchlist = useAppStore((state) => state.watchlist);
  const setWatchlist = useAppStore((state) => state.setWatchlist);
  const defaultRange = useAppStore((state) => state.settings.defaultRange);
  const [stock, setStock] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setStock(null);
    setError("");
    api.get(`/stocks/${encodeURIComponent(symbol)}`)
      .then((result) => { if (active) setStock(result); })
      .catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [symbol]);

  const updateQuote = useCallback((quote) => setStock((current) => current ? { ...current, ...quote } : current), []);
  const listed = watchlist.some((item) => item.symbol === symbol.toUpperCase());

  async function toggleWatchlist() {
    setBusy(true);
    try {
      if (listed) await api.delete(`/watchlist/${encodeURIComponent(symbol)}`);
      else await api.post("/watchlist", { symbol });
      const result = await api.get("/watchlist");
      setWatchlist(result.watchlist);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (!stock && !error) return <Loading label={`Loading ${symbol.toUpperCase()}`} />;
  if (error && !stock) return <div className="page-stack"><Link className="back-link" to="/"><ArrowLeft size={14} /> Back to overview</Link><EmptyState icon={<Star size={17} />} title="Couldn't load this stock" detail={error} action={<button className="button" onClick={() => navigate("/")}>Return home</button>} /></div>;

  return <div className="page-stack stock-page">
    <Link className="back-link" to="/"><ArrowLeft size={14} /> Overview</Link>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <div className="stock-title-row">
      <div className="stock-company-heading">
        <span className="company-symbol">{symbol.slice(0, 1).toUpperCase()}</span>
        <div><div className="eyebrow">{stock.exchange || "MARKET"} <span className="eyebrow-separator">/</span> {stock.symbol}</div><h1>{stock.name}</h1></div>
      </div>
      <button className={`button ${listed ? "button-saved" : ""}`} onClick={toggleWatchlist} disabled={busy}><Star size={15} fill={listed ? "currentColor" : "none"} />{listed ? "In watchlist" : "Add to watchlist"}</button>
    </div>

    <div className="stock-quote-bar panel">
      <div className="primary-quote"><span className="muted">Last price</span><strong>{formatCurrency(stock.price, stock.currency)}</strong><Change value={stock.change} percent={stock.changePercent} /></div>
      <div className="quote-divider" />
      <div className="quote-stat"><span>Market status</span><b><i className={`status-dot ${stock.marketState === "Open" ? "open" : ""}`} />{stock.marketState ?? "Delayed"}</b></div>
      <div className="quote-stat"><span>Volume</span><b>{formatNumber(stock.volume)}</b></div>
      <div className="quote-stat"><span>Market cap</span><b>{stock.marketCap ? formatCurrency(stock.marketCap, stock.currency, true) : "—"}</b></div>
      <div className="quote-stat"><span>P/E ratio</span><b>{Number.isFinite(stock.peRatio) ? stock.peRatio.toFixed(2) : "—"}</b></div>
    </div>

    <section className="panel chart-panel">
      <div className="chart-heading"><div><span className="section-kicker">PRICE HISTORY</span><strong>{stock.symbol} <span>· {stock.currency ?? "USD"}</span></strong></div><span className="chart-market-note">Market data may be delayed</span></div>
      <StockChart key={symbol} symbol={symbol} initialRange={defaultRange ?? "1D"} onQuote={updateQuote} />
    </section>

    <div className="dashboard-columns detail-columns">
      <section className="panel content-panel">
        <SectionHeading title="Key statistics" />
        <div className="stat-grid">
          <Stat label="Previous close" value={formatCurrency(stock.previousClose, stock.currency)} />
          <Stat label="52-week high" value={formatCurrency(stock.fiftyTwoWeekHigh, stock.currency)} />
          <Stat label="52-week low" value={formatCurrency(stock.fiftyTwoWeekLow, stock.currency)} />
          <Stat label="Volume" value={formatNumber(stock.volume)} />
        </div>
        <p className="updated-at">Quote updated {formatTimeAgo(stock.timestamp)}</p>
      </section>
      <section className="panel content-panel">
        <SectionHeading title="Company news" detail="Recent headlines" />
        {stock.news?.length ? stock.news.slice(0, 4).map((item) => <a className="news-row" href={item.url} target="_blank" rel="noreferrer" key={item.url}><span className="news-title">{item.title}</span><span className="news-meta">{item.publisher} · {formatTimeAgo(item.publishedAt)} <ExternalLink size={11} /></span></a>) : <EmptyState icon={<ArrowUpRight size={15} />} title="No recent headlines" detail="No related news is currently available." />}
      </section>
    </div>
    <p className="data-note">Quotes and historical prices use Nasdaq data where available, with Yahoo Finance as a fallback and for company news. Data may be delayed. This is not investment advice.</p>
  </div>;
}

function Stat({ label, value }) {
  return <div className="stat-tile"><span>{label}</span><b>{value}</b></div>;
}
