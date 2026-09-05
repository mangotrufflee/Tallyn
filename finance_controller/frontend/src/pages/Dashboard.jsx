import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

import KPICard from "../components/KPICard";
import WorkflowProgress from "../components/WorkflowProgress";
import { getSummary, getMetrics, getBenchmark } from "../services/api";
import { hasGroundTruth } from "../utils/workflow";

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [benchmark, setBenchmark] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [summaryData, metricsData, benchmarkData] = await Promise.all([
          getSummary(),
          getMetrics(),
          getBenchmark(),
        ]);
        setSummary(summaryData);
        setMetrics(metricsData);
        setBenchmark(benchmarkData);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, []);

  const chartData = useMemo(() => {
    if (!summary) return [];
    return [
      { name: "Matched", value: summary.matched },
      { name: "Review", value: summary.review },
      { name: "Exceptions", value: summary.exceptions },
    ];
  }, [summary]);

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="page-loading">Loading dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-page">
        <div className="page-error">{error}</div>
      </div>
    );
  }

  const matchRate =
    summary.total_transactions > 0
      ? ((summary.matched / summary.total_transactions) * 100).toFixed(1)
      : "0.0";
  const groundTruth = hasGroundTruth(metrics);
  const pending = (summary.review || 0) + (summary.exceptions || 0);
  const workflowStep = pending > 0 ? 4 : summary.total_transactions > 0 ? 5 : 1;

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">FINANCE OPERATIONS CONTROL</span>
          <h1>Reconciliation Overview</h1>
          <p>
            Current uploaded batch and the separate Track 04 evaluation. Quality scores are never shown as if they belong to a live batch without ground truth.
          </p>
        </div>
        <Link to="/new-reconciliation" className="primary-button button-link">
          New Reconciliation
        </Link>
      </div>

      <WorkflowProgress
        currentStep={workflowStep}
        hint={pending > 0 ? `${pending} items still need human review.` : "No open review items in the current batch."}
      />

      <section className="dashboard-section-block">
        <div className="section-kicker-row">
          <div>
            <span className="dashboard-eyebrow">CURRENT RECONCILIATION</span>
            <h2>Live uploaded batch</h2>
            <p>Counts from the records currently in the database after the last upload or seed.</p>
          </div>
          <span className="batch-badge">Current batch</span>
        </div>

        <div className="kpi-grid">
          <KPICard title="Total Transactions" value={summary.total_transactions} subtitle="Current uploaded records" />
          <KPICard title="Matched" value={summary.matched} subtitle={`${matchRate}% of current batch`} type="success" />
          <KPICard title="Needs Review" value={summary.review} subtitle="Human attention required" type="warning" />
          <KPICard title="Exceptions" value={summary.exceptions} subtitle="Could not be resolved" type="danger" />
        </div>

        <div className="dashboard-chart-grid">
          <div className="dashboard-card">
            <div className="card-header">
              <div>
                <h2>Reconciliation Outcomes</h2>
                <p>Distribution of current-batch decisions.</p>
              </div>
            </div>
            <div className="chart-container pie-chart-container">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={65}
                    outerRadius={100}
                    paddingAngle={3}
                  >
                    {chartData.map((entry) => (
                      <Cell key={entry.name} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend verticalAlign="bottom" height={36} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="dashboard-card">
            <div className="card-header">
              <div>
                <h2>Ground-truth quality</h2>
                <p>Accuracy metrics only appear when this batch has labeled expected invoices.</p>
              </div>
            </div>
            {groundTruth ? (
              <div className="performance-grid">
                <div className="performance-item"><span>Accuracy</span><strong>{metrics.accuracy.toFixed(2)}%</strong><small>Current batch vs labels</small></div>
                <div className="performance-item"><span>Precision</span><strong>{metrics.precision.toFixed(2)}%</strong><small>Correct automatic matches</small></div>
                <div className="performance-item"><span>Recall</span><strong>{metrics.recall.toFixed(2)}%</strong><small>True matches recovered</small></div>
                <div className="performance-item"><span>F1 Score</span><strong>{metrics.f1.toFixed(2)}%</strong><small>Balanced quality</small></div>
              </div>
            ) : (
              <div className="ground-truth-unavailable">
                <strong>Ground truth unavailable</strong>
                <p>This uploaded batch has no expected-invoice labels, so Accuracy, Precision, Recall, and F1 are not shown here.</p>
              </div>
            )}
          </div>
        </div>

        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h2>Current pipeline activity</h2>
              <p>Operational counts from the live database, not Track 04.</p>
            </div>
          </div>
          <div className="performance-grid">
            <div className="performance-item"><span>AI Cases</span><strong>{metrics.ai_cases}</strong><small>Uncertain cases sent to AI</small></div>
            <div className="performance-item"><span>AI Recommendations</span><strong>{metrics.ai_recommendations}</strong><small>AI MATCH recommendations</small></div>
            <div className="performance-item"><span>Guard Approved</span><strong>{metrics.guard_approved}</strong><small>AI matches independently verified</small></div>
            <div className="performance-item"><span>Guard Rejected</span><strong>{metrics.ai_matches_blocked}</strong><small>Recommendations stopped</small></div>
            <div className="performance-item"><span>Human Reviewed</span><strong>{metrics.human_reviewed ?? 0}</strong><small>Completed reviewer decisions</small></div>
            <div className="performance-item"><span>Still Unresolved</span><strong>{summary.review + summary.exceptions}</strong><small>Open review and exceptions</small></div>
          </div>
        </div>
      </section>

      <section className="dashboard-section-block benchmark-section">
        <div className="section-kicker-row">
          <div>
            <span className="dashboard-eyebrow">TRACK 04 BENCHMARK</span>
            <h2>Measured evaluation batch</h2>
            <p>These figures come from the saved Track 04 result file. They are not the current upload.</p>
          </div>
          <span className="batch-badge">Track 04</span>
        </div>

        {benchmark?.available ? (
          <div className="dashboard-card">
            <div className="performance-grid">
              <div className="performance-item"><span>Records</span><strong>{benchmark.records}</strong><small>Synthetic evaluation batch</small></div>
              <div className="performance-item"><span>Match Rate</span><strong>{benchmark.match_rate.toFixed(2)}%</strong><small>Final automatic matches</small></div>
              <div className="performance-item"><span>Accuracy</span><strong>{benchmark.accuracy.toFixed(2)}%</strong><small>Labeled Track 04 correctness</small></div>
              <div className="performance-item"><span>Precision</span><strong>—</strong><small>Not returned by /benchmark</small></div>
              <div className="performance-item"><span>Recall</span><strong>—</strong><small>Not returned by /benchmark</small></div>
              <div className="performance-item"><span>F1</span><strong>—</strong><small>Not returned by /benchmark</small></div>
              <div className="performance-item"><span>AI Processed</span><strong>{benchmark.ai_processed}</strong><small>Uncertain cases sent to AI</small></div>
              <div className="performance-item"><span>Guard Verified</span><strong>{benchmark.guard_verified}</strong><small>AI matches independently verified</small></div>
              <div className="performance-item"><span>Unsafe Auto Matches</span><strong>{benchmark.incorrect_automatic}</strong><small>Must remain zero</small></div>
            </div>
          </div>
        ) : (
          <div className="dashboard-card">
            <p className="muted-note">Track 04 benchmark file is not available.</p>
          </div>
        )}
      </section>

      <div className="dashboard-card pipeline-card">
        <div className="card-header">
          <div>
            <h2>Controller Pipeline</h2>
            <p>How a transaction moves from raw data to a controlled financial decision.</p>
          </div>
        </div>
        <div className="controller-pipeline">
          <div className="pipeline-step"><div className="pipeline-number">01</div><strong>Ingest</strong><span>Bank and supporting records enter the controller.</span></div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-step"><div className="pipeline-number">02</div><strong>Reconcile</strong><span>Deterministic rules identify likely matches.</span></div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-step"><div className="pipeline-number">03</div><strong>Reason</strong><span>AI analyzes ambiguous transactions.</span></div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-step pipeline-highlight"><div className="pipeline-number">04</div><strong>Verify</strong><span>Independent controls validate AI decisions.</span></div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-step"><div className="pipeline-number">05</div><strong>Review</strong><span>Humans resolve remaining uncertainty.</span></div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
