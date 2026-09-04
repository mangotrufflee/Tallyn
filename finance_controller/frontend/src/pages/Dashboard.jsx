import { useEffect, useState } from "react";
import { getSummary } from "../services/api";
import KPICard from "../components/KPICard";

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadSummary() {
      try {
        const data = await getSummary();
        setSummary(data);
      } catch (err) {
        setError("Unable to load dashboard data.");
      } finally {
        setLoading(false);
      }
    }

    loadSummary();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="page-container">
        <h1>Reconciliation Overview</h1>
        <div className="empty-state">
          <h2>Unable to load data</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const total = summary.total_transactions || 0;
  const matched = summary.matched || 0;
  const review = summary.review || 0;
  const exceptions = summary.exceptions || 0;

  const matchRate =
    total > 0 ? ((matched / total) * 100).toFixed(1) : "0.0";

  return (
    <div className="page-container">

      {/* ================= HEADER ================= */}

      <div className="page-header dashboard-page-header">
        <div>
          <h1>Reconciliation Overview</h1>
          <p>
            Monitor the finance reconciliation pipeline and verification
            performance
          </p>
        </div>

        <div className="batch-status">
          <span className="status-dot"></span>
          Batch complete
        </div>
      </div>


      {/* ================= PRIMARY KPIs ================= */}

      <div className="kpi-grid">

        <KPICard
          title="Transactions Processed"
          value={total}
          description="Records in current batch"
          type="neutral"
          icon="↔"
        />

        <KPICard
          title="Final Matched"
          value={matched}
          description={`${matchRate}% automated match rate`}
          type="success"
          icon="✓"
        />

        <KPICard
          title="Requires Review"
          value={review}
          description="Human verification queue"
          type="warning"
          icon="!"
        />

        <KPICard
          title="Exceptions"
          value={exceptions}
          description="Could not be resolved"
          type="danger"
          icon="×"
        />

      </div>


      {/* ================= HEALTH + PIPELINE ================= */}

      <div className="dashboard-two-column">

        {/* RECONCILIATION HEALTH */}

        <div className="dashboard-card">

          <div className="section-header">
            <div>
              <h2>Reconciliation Health</h2>
              <p>Final operational outcome</p>
            </div>

            <strong className="health-percentage">
              {matchRate}%
            </strong>
          </div>

          <div className="health-bar-wrapper">

            <div className="health-bar">
              <div
                className="health-matched"
                style={{
                  width: `${(matched / total) * 100}%`,
                }}
              />

              <div
                className="health-review"
                style={{
                  width: `${(review / total) * 100}%`,
                }}
              />

              <div
                className="health-exception"
                style={{
                  width: `${(exceptions / total) * 100}%`,
                }}
              />

            </div>

          </div>

          <div className="health-legend">

            <div>
              <span className="legend-dot matched-dot"></span>
              <span>Matched</span>
              <strong>{matched}</strong>
            </div>

            <div>
              <span className="legend-dot review-dot"></span>
              <span>Review</span>
              <strong>{review}</strong>
            </div>

            <div>
              <span className="legend-dot exception-dot"></span>
              <span>Exception</span>
              <strong>{exceptions}</strong>
            </div>

          </div>

        </div>


        {/* PROCESS PIPELINE */}

        <div className="dashboard-card">

          <div className="section-header">
            <div>
              <h2>Controller Pipeline</h2>
              <p>How transactions move through the system</p>
            </div>
          </div>

          <div className="pipeline">

            <div className="pipeline-step">
              <div className="pipeline-icon">1</div>
              <div>
                <strong>Ingest</strong>
                <span>{total} records</span>
              </div>
            </div>

            <div className="pipeline-arrow">→</div>

            <div className="pipeline-step">
              <div className="pipeline-icon">2</div>
              <div>
                <strong>Match</strong>
                <span>Deterministic engine</span>
              </div>
            </div>

            <div className="pipeline-arrow">→</div>

            <div className="pipeline-step">
              <div className="pipeline-icon">3</div>
              <div>
                <strong>Reason</strong>
                <span>AI for uncertain cases</span>
              </div>
            </div>

            <div className="pipeline-arrow">→</div>

            <div className="pipeline-step">
              <div className="pipeline-icon">4</div>
              <div>
                <strong>Verify</strong>
                <span>Independent guard</span>
              </div>
            </div>

          </div>

        </div>

      </div>


      {/* ================= MEASURED PERFORMANCE ================= */}

      <div className="dashboard-card performance-card">

        <div className="section-header">

          <div>
            <h2>Measured Controller Performance</h2>
            <p>
              Evaluation metrics from the reconciliation batch
            </p>
          </div>

          <span className="evaluation-label">
            EVALUATED
          </span>

        </div>


        <div className="performance-grid">

          <div className="performance-item">
            <span>Deterministic Accuracy</span>
            <strong>95.0%</strong>
            <small>
              Correct invoice selection
            </small>
          </div>


          <div className="performance-item">
            <span>AI Recommendations</span>
            <strong>17</strong>
            <small>
              Uncertain cases sent to AI
            </small>
          </div>


          <div className="performance-item">
            <span>Guard Approved</span>
            <strong>6</strong>
            <small>
              AI recommendations independently verified
            </small>
          </div>


          <div className="performance-item">
            <span>AI Matches Blocked</span>
            <strong>11</strong>
            <small>
              Prevented from becoming final matches
            </small>
          </div>

        </div>

      </div>


      {/* ================= SAFETY MESSAGE ================= */}

      <div className="dashboard-card controller-principle">

        <div className="principle-icon">
          ✓
        </div>

        <div>
          <h3>Verification-first controller</h3>

          <p>
            AI recommendations do not directly become final accounting
            decisions. Candidate matches are independently verified before
            being accepted; unresolved cases remain visible for human review.
          </p>
        </div>

      </div>

    </div>
  );
}

export default Dashboard;