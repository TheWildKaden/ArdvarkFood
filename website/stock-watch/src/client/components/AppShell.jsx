import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChartLineUp, Gear, House as HouseIcon, ListBullets, Palette as PaletteIcon, Sparkle, SquaresFour, Waveform } from "@phosphor-icons/react";
import { ChevronLeft, ChevronRight, Menu, Search } from "lucide-react";
import { discoveredApps } from "../apps/registry.js";
import { useAppStore } from "../state/store.js";
import GlobalSearch from "./GlobalSearch.jsx";
import Player from "../../../Apps/Spotify/components/Player.jsx";

const iconMap = {
  "layout-dashboard": SquaresFour,
  "list-filter": ListBullets,
  palette: PaletteIcon,
  settings: Gear,
  "audio-lines": Waveform,
  activity: ChartLineUp,
  house: HouseIcon,
  "chart-no-axes-combined": ChartLineUp,
};

export default function AppShell({ children }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar-collapsed") === "true");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const location = useLocation();
  const settings = useAppStore((state) => state.settings);

  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
      if (event.key === "Escape") { setSearchOpen(false); setMobileOpen(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => setMobileOpen(false), [location.pathname]);
  const orderedApps = useMemo(() => {
    const favorites = settings.favoriteApps ?? [];
    return [...discoveredApps].sort((a, b) => Number(favorites.includes(b.id)) - Number(favorites.includes(a.id)) || (a.order ?? 100) - (b.order ?? 100));
  }, [settings.favoriteApps]);

  function toggleCollapsed() {
    setCollapsed((current) => {
      localStorage.setItem("sidebar-collapsed", String(!current));
      return !current;
    });
  }

  return <div className={`app-frame ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-nav-open" : ""}`}>
    <aside className="sidebar" aria-label="Application navigation">
      <div className="brand">
        <div className="brand-mark"><span /></div>
        {!collapsed && <div className="brand-copy"><strong>KADEN'S</strong><span>STOCK WATCH</span></div>}
        <button className="sidebar-collapse" onClick={toggleCollapsed} title={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>{collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}</button>
      </div>
      <button className="sidebar-search" onClick={() => setSearchOpen(true)} title="Search stocks (Ctrl/⌘ K)" aria-label="Search stocks">
        <Search size={15} /><span>Search anything</span><kbd>Ctrl/⌘ K</kbd>
      </button>
      <div className="sidebar-label">{!collapsed && "APPS"}</div>
      <nav className="app-nav" id="app-navigation" aria-label="Applications">
        {orderedApps.map((app) => {
          const Icon = iconMap[app.icon] ?? Sparkle;
          return <NavLink key={app.id} end={app.route === "/"} to={app.route} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`} title={collapsed ? app.name : undefined}>
            {({ isActive }) => <><Icon size={18} weight={isActive ? "fill" : "regular"} /><span>{app.name}</span>{(settings.favoriteApps ?? []).includes(app.id) && !collapsed && <span className="nav-favorite">•</span>}</>}
          </NavLink>;
        })}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-bottom">
        <div className="user-chip"><span className="avatar">K</span>{!collapsed && <span className="user-name">Local profile</span>}{!collapsed && <span className="user-menu">•••</span>}</div>
      </div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <main className="main-region">
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setMobileOpen((value) => !value)} aria-label={mobileOpen ? "Close navigation" : "Open navigation"} aria-expanded={mobileOpen} aria-controls="app-navigation"><Menu size={18} /></button>
        <div className="breadcrumbs"><strong>{currentLabel(location.pathname)}</strong></div>
        <div className="topbar-actions">
          <button className="topbar-search" onClick={() => setSearchOpen(true)} aria-label="Search stocks" title="Search stocks (Ctrl/⌘ K)"><Search size={14} /><span>Search stocks</span><kbd>Ctrl/⌘ K</kbd></button>
        </div>
      </header>
      <div className="page-content">{children}</div>
      <Player compact />
      <footer className="app-footer"><span>KADEN'S STOCK WATCH <span className="footer-version">· LOCAL APP</span></span><span>Data for informational purposes only</span></footer>
    </main>
    {searchOpen && <GlobalSearch onClose={() => setSearchOpen(false)} />}
  </div>;
}

function currentLabel(pathname) {
  const app = discoveredApps.find((item) => item.route === pathname);
  if (app) return app.name;
  if (pathname.startsWith("/stock/")) return pathname.split("/").at(-1)?.toUpperCase() ?? "Stock";
  return "Stock Watch";
}
