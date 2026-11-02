import { lazy } from "react";

const manifests = import.meta.glob("../../../Apps/*/manifest.json", { eager: true, import: "default" });
const modules = import.meta.glob("../../../Apps/*/index.jsx");

export const discoveredApps = Object.entries(manifests)
  .map(([manifestPath, manifest]) => {
    const modulePath = manifestPath.replace("manifest.json", "index.jsx");
    const load = modules[modulePath];
    if (!manifest?.id || !manifest?.name || !manifest?.route || !load) return null;
    return {
      ...manifest,
      component: lazy(load),
      load,
      permissions: manifest.permissions ?? [],
      settings: manifest.settings ?? [],
    };
  })
  .filter(Boolean)
  .sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.name.localeCompare(b.name));
