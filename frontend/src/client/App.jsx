import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./services/api.js";
import { useAppStore } from "./state/store.js";
import { discoveredApps } from "./apps/registry.js";
import AppShell from "./components/AppShell.jsx";
import { Loading } from "./components/ui.jsx";
import WelcomeScreen from "./components/WelcomeScreen.jsx";

const StockPage = lazy(() => import("./pages/StockPage.jsx"));

export default function App() {
  const [entered, setEntered] = useState(false);
  const appEntryRef = useRef(null);
  const setSettings = useAppStore((state) => state.setSettings);
  const setWatchlist = useAppStore((state) => state.setWatchlist);

  useEffect(() => {
    Promise.all([api.get("/settings"), api.get("/watchlist")])
      .then(([settingsResult, watchlistResult]) => {
        setSettings(settingsResult.settings);
        setWatchlist(watchlistResult.watchlist);
      })
      .catch((error) => console.error("Unable to initialize saved app state", error));
  }, [setSettings, setWatchlist]);

  const settings = useAppStore((state) => state.settings);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const applyTheme = () => {
      document.documentElement.dataset.theme = settings.theme === "system"
        ? (media.matches ? "light" : "dark")
        : settings.theme;
    };
    applyTheme();
    if (settings.theme !== "system") return undefined;
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [settings.theme, settings.accent, settings.compactMode]);

  useEffect(() => {
    document.documentElement.dataset.accent = settings.accent ?? "blue";
    document.documentElement.dataset.density = settings.compactMode ? "compact" : "comfortable";
  }, [settings.accent, settings.compactMode]);

  useEffect(() => {
    if (appEntryRef.current) appEntryRef.current.inert = !entered;
  }, [entered]);

  return (
    <>
      <div ref={appEntryRef} className={entered ? "app-entry app-entry-entered" : "app-entry"} aria-hidden={!entered}>
        <AppShell>
          <Suspense fallback={<Loading label="Opening workspace" />}>
            <Routes>
              {discoveredApps.map((app) => <Route key={app.id} path={app.route} element={<AppRuntime app={app} />} />)}
              <Route path="/stock/:symbol" element={<StockPage />} />
              <Route path="/status" element={<Navigate to="/logger" replace />} />
              <Route path="*" element={<AppRuntime app={discoveredApps.find((app) => app.id === "home") ?? discoveredApps[0]} />} />
            </Routes>
          </Suspense>
        </AppShell>
      </div>
      {!entered && <WelcomeScreen onEnter={() => setEntered(true)} />}
    </>
  );
}

function AppRuntime({ app }) {
  useEffect(() => {
    let active = true;
    let cleanup;
    app.load().then((appModule) => {
      if (!active) return;
      const dispose = appModule.init?.();
      cleanup = () => {
        if (typeof dispose === "function") dispose();
        appModule.cleanup?.();
      };
    }).catch((error) => console.error(`Unable to initialize app "${app.id}"`, error));
    return () => {
      active = false;
      cleanup?.();
    };
  }, [app.id, app.load]);
  return <app.component />;
}
