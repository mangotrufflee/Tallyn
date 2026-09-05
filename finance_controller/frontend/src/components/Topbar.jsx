import { Link } from "react-router-dom";

function Topbar({ compact = false }) {
  return (
    <header className={`topbar ${compact ? "topbar-compact" : ""}`}>
      <div className="brand-wrap">
        <div className="brand-icon">T</div>
        <div>
          <h1>Tallyn</h1>
          <p>Finance Control</p>
        </div>
      </div>

      <div className="topbar-right">
        <Link to="/new-reconciliation" className="primary-button button-link">
          New Reconciliation
        </Link>
      </div>
    </header>
  );
}

export default Topbar;