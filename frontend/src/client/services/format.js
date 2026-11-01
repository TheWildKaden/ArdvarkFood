export function formatCurrency(value, currency = "USD", compact = false) {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency, maximumFractionDigits: value < 1 ? 4 : 2,
    notation: compact ? "compact" : "standard",
  }).format(value);
}

export function formatNumber(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value) : "—";
}

export function formatCompact(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value) : "—";
}

export function formatPercent(value) {
  if (!Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function signed(value) {
  return Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}` : "—";
}

export function formatTimeAgo(input) {
  if (!input) return "Recently";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(input).getTime()) / 1000));
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
