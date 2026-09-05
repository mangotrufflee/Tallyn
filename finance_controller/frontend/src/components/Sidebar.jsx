import { NavLink, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { getSummary } from "../services/api";

function Sidebar() {
  const [summary, setSummary] = useState(null);
  const location = useLocation();

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [location.pathname]);

  const review = summary?.review || 0;
  const exceptions = summary?.exceptions || 0;

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">₿</div>
        <div>
          <h2>Finance</h2>
          <span>Controller</span>
        </div>
      </div>

      <nav className="navigation">
        <div className="nav-section">
          <p className="nav-label">WORKFLOW</p>

          <NavLink to="/dashboard" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} end>
            <span>▦</span>
            Dashboard
          </NavLink>

          <NavLink
            to="/transactions"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <span>↔</span>
            Transactions
          </NavLink>

          <NavLink
            to="/ai-cases"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <span>⚠</span>
            AI Cases
            {exceptions > 0 && <em className="nav-badge">{exceptions}</em>}
          </NavLink>

          <NavLink
            to="/verification"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <span>✓</span>
            Verification
            {review > 0 && <em className="nav-badge">{review}</em>}
          </NavLink>

          <NavLink
            to="/ai-insights"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <span>✦</span>
            AI Insights
          </NavLink>
        </div>
      </nav>

      <div className="system-status">
        <div className="status-dot"></div>
        <div>
          <strong>System Online</strong>
          <span>
            {review + exceptions > 0
              ? `${review + exceptions} items need review`
              : "No pending review"}
          </span>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
