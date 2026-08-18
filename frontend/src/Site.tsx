const SITE_TITLE = "Quant Ranger Dashboard";

export default function Site() {
  return (
    <>
      <nav aria-label="Breadcrumb" className="site-navigation">
        <span aria-current="page" className="site-title">
          {SITE_TITLE}
        </span>
      </nav>
      <main>
        <header className="dashboard-header">
          <h1>Repository maintenance</h1>
          <p>The frontend is ready for browser-readable updater reports.</p>
        </header>
      </main>
    </>
  );
}
