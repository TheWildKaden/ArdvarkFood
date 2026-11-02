import { create } from "zustand";

const defaults = {
  theme: "dark", accent: "blue", compactMode: false, showNews: true,
  defaultRange: "1D", favoriteApps: ["home", "watchlist"],
};

export const useAppStore = create((set) => ({
  watchlist: [],
  settings: defaults,
  setWatchlist: (watchlist) => set({ watchlist }),
  setSettings: (settings) => set({ settings: { ...defaults, ...settings } }),
}));
