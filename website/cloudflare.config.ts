import { defineConfig } from "cf/config";

// The Vimniscient website: static files from public/, nothing else.
export default defineConfig({
  worker: {
    name: "vimniscient",
    compatibilityDate: "2026-09-21",
    observability: { enabled: true },
    assets: {
      htmlHandling: "auto-trailing-slash",
      notFoundHandling: "404-page",
    },
    domains: ["vimniscient.com", "www.vimniscient.com"],
    workersDev: false, // the account has no workers.dev subdomain; the site lives on its domains
  },
});
