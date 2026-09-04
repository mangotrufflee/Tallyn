function Topbar() {
  return (
    <header className="topbar">

      <div>
        <h1>Reconciliation Overview</h1>

        <p>
          Monitor your finance reconciliation pipeline
        </p>
      </div>

      <div className="topbar-right">

        <div className="live-indicator">
          <span></span>
          Live
        </div>

        <div className="avatar">
          AC
        </div>

      </div>

    </header>
  );
}

export default Topbar;