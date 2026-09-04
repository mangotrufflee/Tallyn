import { NavLink } from "react-router-dom";


function Sidebar() {

  return (

    <aside className="sidebar">

      {/* BRAND */}

      <div className="brand">

        <div className="brand-icon">
          ₿
        </div>

        <div>
          <h2>Finance</h2>
          <span>Controller</span>
        </div>

      </div>


      {/* NAVIGATION */}

      <nav className="navigation">

        {/* WORKSPACE */}

        <div className="nav-section">

          <p className="nav-label">
            WORKSPACE
          </p>


          <NavLink
            to="/"
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <span>▦</span>
            Overview
          </NavLink>


          <NavLink
            to="/transactions"
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <span>↔</span>
            Transactions
          </NavLink>


          <NavLink
            to="/exceptions"
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <span>⚠</span>
            Exceptions
          </NavLink>

        </div>


        {/* INTELLIGENCE */}

        <div className="nav-section">

          <p className="nav-label">
            INTELLIGENCE
          </p>


          <NavLink
            to="/ai-insights"
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <span>✦</span>
            AI Insights
          </NavLink>


          <NavLink
            to="/verification"
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <span>✓</span>
            Verification
          </NavLink>

        </div>

      </nav>


      {/* SYSTEM STATUS */}

      <div className="system-status">

        <div className="status-dot"></div>

        <div>

          <strong>
            System Online
          </strong>

          <span>
            AI engine connected
          </span>

        </div>

      </div>

    </aside>

  );
}


export default Sidebar;