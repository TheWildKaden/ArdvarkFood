import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, LoaderCircle } from "lucide-react";
import { formatPercent } from "../services/format.js";
import { toSparklinePoints } from "../../../packages/charts/types/Sparkline.js";

export function Change({ value, percent, className = "" }) {
  if (!Number.isFinite(percent)) return <span className={`change neutral ${className}`}>—</span>;
  const positive = percent >= 0;
  const Icon = positive ? ArrowUpRight : ArrowDownRight;
  return <span className={`change ${positive ? "positive" : "negative"} ${className}`}><Icon size={13} strokeWidth={2.1} />{formatPercent(percent)}</span>;
}

export function SectionHeading({ title, detail, action }) {
  return <div className="section-heading"><div><h2>{title}</h2>{detail && <span>{detail}</span>}</div>{action}</div>;
}

export function EmptyState({ icon, title, detail, action }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><strong>{title}</strong><p>{detail}</p>{action}</div>;
}

export function Loading({ label = "Loading" }) {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={18} />{label}</div>;
}

const sparklineCache = new Map();
export function Sparkline({ symbol, positive = true }) {
  const [values, setValues] = useState(sparklineCache.get(symbol) ?? []);
  useEffect(() => {
    if (sparklineCache.has(symbol)) return;
    let active = true;
    fetch(`/api/stocks/${encodeURIComponent(symbol)}/chart?range=1D`)
      .then((response) => response.ok ? response.json() : null)
      .then((result) => {
        const points = result?.points?.slice(-18).map((point) => point.value) ?? [];
        if (active) { sparklineCache.set(symbol, points); setValues(points); }
      })
      .catch(() => {});
    return () => { active = false; };
  }, [symbol]);
  const width = 66;
  const height = 24;
  if (values.length < 2) return <span className="sparkline-placeholder" aria-hidden="true" />;
  const points = toSparklinePoints(values, width, height);
  return <svg className={`sparkline ${positive ? "spark-positive" : "spark-negative"}`} viewBox={`0 0 ${width} ${height}`} aria-hidden="true"><polyline points={points} /></svg>;
}
