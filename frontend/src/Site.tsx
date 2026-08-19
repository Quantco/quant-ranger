import { useEffect, useState } from "react";

import CopierDashboard from "./copier/CopierDashboard";
import type { DashboardSnapshot } from "./copier/dashboard";
import { fetchJson } from "./data";
import Overview from "./Overview";

const SITE_TITLE = "Quant Ranger Dashboard";
const COPIER_TITLE = "Copier Dashboard";
const COPIER_DATA_PATH = "data/copier/latest.json";

type Route = { kind: "copier" } | { kind: "overview" } | { kind: "unknown" };
type Page = { kind: "copier"; snapshot: DashboardSnapshot } | { kind: "overview" } | { kind: "unknown" };

function currentRoute(): Route {
  const hash = window.location.hash;
  const path = hash.replace(/^#\/?/, "").split("?", 1)[0];
  if (path === "") return { kind: "overview" };
  return path === "copier" ? { kind: "copier" } : { kind: "unknown" };
}

async function loadPage(route: Route): Promise<Page> {
  if (route.kind !== "copier") return route;
  const snapshot = await fetchJson<DashboardSnapshot>(`./${COPIER_DATA_PATH}`);
  if (snapshot == null) throw new Error("No Copier report data was found.");
  return { kind: "copier", snapshot };
}

export default function Site() {
  const [route, setRoute] = useState(currentRoute);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const updateRoute = () => setRoute(currentRoute());
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  useEffect(() => {
    let current = true;
    setPage(null);
    setError("");
    loadPage(route).then(
      (loaded) => current && setPage(loaded),
      (reason) => current && setError(reason instanceof Error ? reason.message : String(reason)),
    );
    return () => {
      current = false;
    };
  }, [route]);

  useEffect(() => {
    document.title = route.kind === "copier" ? `${COPIER_TITLE} · ${SITE_TITLE}` : SITE_TITLE;
    window.scrollTo({ top: 0 });
  }, [route]);

  return (
    <>
      <nav aria-label="Breadcrumb" className="site-navigation">
        {route.kind === "overview" ? (
          <span aria-current="page" className="site-title">
            {SITE_TITLE}
          </span>
        ) : (
          <a className="site-title" href="#/">
            {SITE_TITLE}
          </a>
        )}
        {route.kind === "copier" && (
          <>
            <span aria-hidden="true" className="breadcrumb-separator">
              /
            </span>
            <span aria-current="page">{COPIER_TITLE}</span>
          </>
        )}
      </nav>
      {error ? (
        <main className="standalone-state">
          <h1>Copier dashboard unavailable</h1>
          <p>{error}</p>
          <div className="data-message">
            <p>
              Expected a generated report at <code>{COPIER_DATA_PATH}</code>.
            </p>
            <a href="#/">Return to the dashboard</a>
          </div>
        </main>
      ) : page == null ? (
        <main>
          <p>Loading…</p>
        </main>
      ) : page.kind === "overview" ? (
        <Overview />
      ) : page.kind === "copier" ? (
        <CopierDashboard snapshot={page.snapshot} />
      ) : (
        <main>
          <h1>Page not found</h1>
          <p>
            Return to the <a href="#/">dashboard overview</a>.
          </p>
        </main>
      )}
    </>
  );
}
