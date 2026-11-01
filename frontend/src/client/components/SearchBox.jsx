import { useEffect, useRef, useState } from "react";
import { Command, Search, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api.js";
import { Change } from "./ui.jsx";
import { formatCurrency } from "../services/format.js";

export default function SearchBox({ compact = false, placeholder = "Search ticker or company", onSelect }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const timer = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (query.trim().length < 1) { setResults([]); setError(""); return; }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await api.get(`/search?q=${encodeURIComponent(query.trim())}`);
        setResults(response.results);
        setError("");
        setActive(0);
      } catch (e) { setError(e.message); setResults([]); }
      finally { setLoading(false); }
    }, 220);
    return () => window.clearTimeout(timer.current);
  }, [query]);

  function select(stock) {
    setOpen(false);
    if (onSelect) onSelect(stock);
    else navigate(`/stock/${encodeURIComponent(stock.symbol)}`);
    setQuery("");
  }

  function onKeyDown(event) {
    if (event.key === "ArrowDown" && results.length) { event.preventDefault(); setActive((active + 1) % results.length); }
    if (event.key === "ArrowUp" && results.length) { event.preventDefault(); setActive((active - 1 + results.length) % results.length); }
    if (event.key === "Enter" && results[active]) { event.preventDefault(); select(results[active]); }
    if (event.key === "Escape") setOpen(false);
  }

  return <div className={`search-box ${compact ? "search-compact" : ""}`}>
    <Search size={compact ? 15 : 16} className="search-icon" />
    <input value={query} onChange={(event) => setQuery(event.target.value)} onFocus={() => setOpen(true)} onKeyDown={onKeyDown} placeholder={placeholder} aria-label={placeholder} aria-expanded={open && query.length > 0} aria-controls="stock-search-results" autoComplete="off" />
    {!compact && <kbd><Command size={11} /> K</kbd>}
    {open && query.length > 0 && <div className="search-results" id="stock-search-results" role="listbox">
      {loading ? <div className="search-message">Searching market data…</div>
        : error ? <div className="search-message search-error">{error}</div>
          : results.length ? results.map((stock, index) => <button className={`search-result ${index === active ? "selected" : ""}`} role="option" aria-selected={index === active} key={stock.symbol} onMouseEnter={() => setActive(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => select(stock)}>
            <span className="search-result-icon"><TrendingUp size={15} /></span><span className="search-result-name"><b>{stock.symbol}</b><small>{stock.name} · {stock.exchange || "Market"}</small></span><span className="search-result-quote"><b>{formatCurrency(stock.price)}</b><Change percent={stock.changePercent} /></span>
          </button>)
            : <div className="search-message">No matching stocks found.</div>}
      <div className="search-footer"><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><kbd>↵</kbd> to open</span></div>
    </div>}
  </div>;
}
