import { getDatabase } from "../../../packages/storage/sqlite.js";

export function initializeDatabase() {
  return getDatabase();
}

function db() {
  return getDatabase();
}

export function getWatchlist() {
  return db().prepare("SELECT symbol, position, added_at AS addedAt FROM watchlist ORDER BY position, added_at").all();
}

export function addToWatchlist(symbol) {
  const position = db().prepare("SELECT COALESCE(MAX(position), -1) + 1 AS nextPosition FROM watchlist").get().nextPosition;
  db().prepare("INSERT OR IGNORE INTO watchlist (symbol, position) VALUES (?, ?)").run(symbol, position);
  return getWatchlist();
}

export function removeFromWatchlist(symbol) {
  const remove = db().transaction(() => {
    db().prepare("DELETE FROM watchlist WHERE symbol = ?").run(symbol);
    const rows = db().prepare("SELECT symbol FROM watchlist ORDER BY position, added_at").all();
    const update = db().prepare("UPDATE watchlist SET position = ? WHERE symbol = ?");
    rows.forEach(({ symbol: item }, index) => update.run(index, item));
  });
  remove();
  return getWatchlist();
}

export function reorderWatchlist(symbols) {
  const update = db().prepare("UPDATE watchlist SET position = ? WHERE symbol = ?");
  db().transaction((items) => items.forEach((symbol, index) => update.run(index, symbol)))(symbols);
  return getWatchlist();
}

export function getSettings() {
  return Object.fromEntries(db().prepare("SELECT key, value FROM settings").all().map(({ key, value }) => [key, JSON.parse(value)]));
}

export function updateSettings(settings) {
  const upsert = db().prepare("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value");
  db().transaction((entries) => entries.forEach(([key, value]) => upsert.run(key, JSON.stringify(value))))(Object.entries(settings));
  return getSettings();
}

export function addRecentlyViewed(symbol) {
  db().transaction(() => {
    db().prepare("INSERT INTO recently_viewed (symbol, viewed_at) VALUES (?, CURRENT_TIMESTAMP) ON CONFLICT(symbol) DO UPDATE SET viewed_at = CURRENT_TIMESTAMP").run(symbol);
    db().prepare("DELETE FROM recently_viewed WHERE symbol NOT IN (SELECT symbol FROM recently_viewed ORDER BY viewed_at DESC LIMIT 8)").run();
  })();
}

export function getRecentlyViewed() {
  return db().prepare("SELECT symbol, viewed_at AS viewedAt FROM recently_viewed ORDER BY viewed_at DESC LIMIT 8").all();
}
