import { useEffect, useRef, useState } from "react";
import { api } from "../services/api.js";
import { ChartEngine } from "../../../packages/charts/ChartEngine.js";
import ChartControls from "../../../packages/charts/ChartControls.jsx";
import ChartTooltip from "../../../packages/charts/ChartTooltip.jsx";

export default function StockChart({ symbol, initialRange = "1D", onQuote }) {
  const host = useRef(null);
  const engine = useRef(null);
  const data = useRef(null);
  const [range, setRange] = useState(initialRange);
  const [type, setType] = useState("area");
  const [showVolume, setShowVolume] = useState(false);
  const [hover, setHover] = useState(null);
  const [state, setState] = useState({ loading: true, error: "", points: [] });
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? "dark");

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme ?? "dark"));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!host.current) return undefined;
    const instance = new ChartEngine(host.current, {
      type,
      showVolume,
      theme,
      onCrosshairMove: setHover,
    });
    engine.current = instance;
    if (data.current) instance.setData(data.current);
    return () => { instance.remove(); engine.current = null; };
  }, [type, showVolume, theme]);

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: "" }));
    api.get(`/stocks/${encodeURIComponent(symbol)}/chart?range=${range}`)
      .then((result) => {
        if (!active) return;
        data.current = result;
        setState({ loading: false, error: "", points: result.points });
        onQuote?.(result.quote);
        engine.current?.setData(result);
      })
      .catch((error) => { if (active) setState({ loading: false, error: error.message, points: [] }); });
    return () => { active = false; };
  }, [symbol, range, onQuote]);

  return <div className="chart-module">
    <ChartControls
      range={range}
      onRange={setRange}
      type={type}
      onType={setType}
      showVolume={showVolume}
      onToggleVolume={() => setShowVolume((value) => !value)}
      onExport={() => data.current && engine.current?.exportCsv(data.current, symbol, range)}
    />
    <ChartTooltip symbol={symbol} currency={data.current?.currency} data={hover} />
    {state.loading && <div className="chart-loading">Loading price history…</div>}
    {state.error && <div className="chart-error" role="alert">Chart unavailable: {state.error}</div>}
    {!state.loading && !state.error && state.points.length === 0 && <div className="chart-error">No historical data available for this range.</div>}
    <div ref={host} className="chart-canvas" role="img" aria-label={`${symbol} stock price chart`} />
  </div>;
}
