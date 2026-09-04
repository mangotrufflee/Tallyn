import { useEffect, useState } from "react";

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
        console.error(err);
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
    <>
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


      <section className="dashboard-card">

        <div className="section-header">

          <div>
            <h2>Reconciliation Health</h2>

            <p>
              Percentage of transactions successfully matched
            </p>
          </div>

          <strong className="health-percentage">
            {matchRate.toFixed(1)}%
          </strong>

        </div>


        <div className="progress-container">

          <div
            className="progress-bar"
            style={{
              width: `${matchRate}%`,
            }}
          />

        </div>


        <div className="progress-labels">

          <span>
            {summary.matched} matched
          </span>

          <span>
            {summary.review + summary.exceptions} require attention
          </span>

        </div>

      </section>


      <section className="dashboard-card">

        <div className="section-header">

          <div>
            <h2>Reconciliation Pipeline</h2>

            <p>
              How transactions move through the finance controller
            </p>
          </div>

        </div>


        <div className="pipeline">

          <div className="pipeline-step">

            <div className="pipeline-icon">
              01
            </div>

            <div>
              <strong>Bank Data</strong>
              <span>Source transactions</span>
            </div>

          </div>


          <div className="pipeline-arrow">→</div>


          <div className="pipeline-step">

            <div className="pipeline-icon">
              02
            </div>

            <div>
              <strong>Matching</strong>
              <span>Deterministic rules</span>
            </div>

          </div>


          <div className="pipeline-arrow">→</div>


          <div className="pipeline-step ai-step">

            <div className="pipeline-icon">
              ✦
            </div>

            <div>
              <strong>AI Reasoning</strong>
              <span>Qwen analysis</span>
            </div>

          </div>


          <div className="pipeline-arrow">→</div>


          <div className="pipeline-step">

            <div className="pipeline-icon">
              04
            </div>

            <div>
              <strong>Verification</strong>
              <span>Independent guard</span>
            </div>

          </div>


          <div className="pipeline-arrow">→</div>


          <div className="pipeline-step">

            <div className="pipeline-icon">
              ✓
            </div>

            <div>
              <strong>Final Decision</strong>
              <span>Match or review</span>
            </div>

          </div>

        </div>

      </section>

    </>
  );
}

export default Dashboard;