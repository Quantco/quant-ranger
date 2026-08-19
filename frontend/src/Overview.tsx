import "./Overview.css";

export default function Overview() {
  return (
    <main className="dashboard-overview">
      <header className="dashboard-header">
        <h1>Overview</h1>
        <p>Explore quant-ranger activity and reports.</p>
      </header>

      <section aria-labelledby="copier-dashboard-heading" className="dashboard-overview-section">
        <div className="dashboard-overview-section-heading">
          <h2 id="copier-dashboard-heading">Copier Dashboard</h2>
        </div>
        <a className="dashboard-overview-card" href="#/copier">
          <span className="dashboard-overview-card-content">
            <strong>Copier repositories</strong>
            <span>Compare template versions, validation results, and Copier answers.</span>
          </span>
          <span className="dashboard-overview-card-action">
            Open
            <svg aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 16 16">
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </span>
        </a>
      </section>
    </main>
  );
}
