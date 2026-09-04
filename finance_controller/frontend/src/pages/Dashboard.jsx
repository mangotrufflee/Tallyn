import { useEffect, useState } from "react";

import "../App.css";
import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";
import KPICard from "../components/KPICard";

import { getSummary } from "../services/api";

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSummary()
      .then((data) => {
        setSummary(data);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, []);

  if (error) {
    return (
      <div className="error-page">
        <h2>Unable to load dashboard</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="loading-page">
        <div className="loader"></div>
        <p>Loading finance data...</p>
      </div>
    );
  }

  const matchRate =
    (summary.matched / summary.total_transactions) * 100;

  return (
    <div className="app">

      <Sidebar />

      <main className="main-content">

        <Topbar />

        <section className="kpi-grid">

          <KPICard
            title="Total Transactions"
            value={summary.total_transactions}
            description="Records processed"
            icon="#"
          />

          <KPICard
            title="Matched"
            value={summary.matched}
            description={`${matchRate.toFixed(1)}% match rate`}
            type="success"
            icon="✓"
          />

          <KPICard
            title="Needs Review"
            value={summary.review}
            description="Requires human verification"
            type="warning"
            icon="!"
          />

          <KPICard
            title="Exceptions"
            value={summary.exceptions}
            description="Unable to resolve"
            type="danger"
            icon="×"
          />

        </section>

      </main>

    </div>
  );
}

export default Dashboard;