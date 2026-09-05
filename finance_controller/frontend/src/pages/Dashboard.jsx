import { useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

import KPICard from "../components/KPICard";
import { getSummary, getMetrics, getBenchmark } from "../services/api";

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
      {
        name: "Matched",
        value: summary.matched,
      },
      {
        name: "Review",
        value: summary.review,
      },
      {
        name: "Exceptions",
        value: summary.exceptions,
      },
    ];
  }, [summary]);

  const performanceData = useMemo(() => {
    if (!metrics) return [];

    return [
      { name: "Accuracy", value: metrics.accuracy ?? metrics.deterministic_accuracy },
      { name: "Precision", value: metrics.precision ?? 0 },
      { name: "Recall", value: metrics.recall ?? 0 },
      { name: "F1", value: metrics.f1 ?? 0 },
    ];
  }, [metrics]);

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="page-loading">
          Loading dashboard...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-page">
        <div className="page-error">
          {error}
        </div>
      </div>
    );
  }

  const matchRate =
    summary.total_transactions > 0
      ? (
          (summary.matched / summary.total_transactions) *
          100
        ).toFixed(1)
      : "0.0";

  return (
    <div className="dashboard-page">

      {/* HEADER */}

      <div className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">
            FINANCE OPERATIONS CONTROL
          </span>

          <h1>Reconciliation Overview</h1>

          <p>
            Monitor transaction matching, AI-assisted decisions,
            verification controls and unresolved exceptions.
          </p>
        </div>

        <div className="dashboard-status">
          <span className="status-dot"></span>
          Live database
        </div>
      </div>


      {/* KPI ROW */}

      <div className="kpi-grid">

        <KPICard
          title="Total Transactions"
          value={summary.total_transactions}
          subtitle="Records processed"
        />

        <KPICard
          title="Matched"
          value={summary.matched}
          subtitle={`${matchRate}% automated match rate`}
        />

        <KPICard
          title="Needs Review"
          value={summary.review}
          subtitle="Human attention required"
        />

        <KPICard
          title="Exceptions"
          value={summary.exceptions}
          subtitle="Could not be resolved"
        />

      </div>


      {/* MEASURED QUALITY */}

      <div className="kpi-grid">

        <KPICard
          title="Accuracy"
          value={`${(metrics.accuracy ?? 0).toFixed(2)}%`}
          subtitle="Ground-truth reconciliation accuracy"
        />

        <KPICard
          title="Precision"
          value={`${(metrics.precision ?? 0).toFixed(2)}%`}
          subtitle="Correct automatic matches"
        />

        <KPICard
          title="Recall"
          value={`${(metrics.recall ?? 0).toFixed(2)}%`}
          subtitle="True matches recovered"
        />

        <KPICard
          title="F1 Score"
          value={`${(metrics.f1 ?? 0).toFixed(2)}%`}
          subtitle="Balanced reconciliation quality"
        />

      </div>

      {benchmark?.available && (
        <div className="dashboard-card" style={{ marginBottom: "24px" }}>
          <div className="card-header">
            <div>
              <h2>Track 04 Benchmark</h2>
              <p>Measured on the 500-record synthetic evaluation batch.</p>
            </div>
            <div className="dashboard-status">
              <span className="status-dot"></span>
              Benchmark ready
            </div>
          </div>

          <div className="performance-grid">
            <div className="performance-item"><span>Records</span><strong>{benchmark.records}</strong><small>Processed end-to-end</small></div>
            <div className="performance-item"><span>Match Rate</span><strong>{benchmark.match_rate.toFixed(2)}%</strong><small>Final automatic matches</small></div>
            <div className="performance-item"><span>AI Processed</span><strong>{benchmark.ai_processed}</strong><small>Uncertain cases sent to AI</small></div>
            <div className="performance-item"><span>Guard Verified</span><strong>{benchmark.guard_verified}</strong><small>AI matches independently verified</small></div>
            <div className="performance-item"><span>AI Matches</span><strong>{benchmark.ai_matches}</strong><small>AI recommendations</small></div>
            <div className="performance-item"><span>Unsafe Auto Matches</span><strong>{benchmark.incorrect_automatic}</strong><small>Must remain zero</small></div>
          </div>
        </div>
      )}

      {/* MAIN CHART ROW */}

      <div className="dashboard-chart-grid">

        {/* RECONCILIATION OUTCOMES */}

        <div className="dashboard-card">

          <div className="card-header">
            <div>
              <h2>Reconciliation Outcomes</h2>

              <p>
                Distribution of final transaction decisions.
              </p>
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
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} />
                  ))}
                </Pie>

                <Tooltip />

                <Legend
                  verticalAlign="bottom"
                  height={36}
                />

              </PieChart>

            </ResponsiveContainer>

          </div>

        </div>


        {/* PERFORMANCE */}

        <div className="dashboard-card">

          <div className="card-header">

            <div>

              <h2>Measured Performance</h2>

              <p>
                Accuracy and approval metrics from evaluation data.
              </p>

            </div>

          </div>

          <div className="chart-container">

            <ResponsiveContainer width="100%" height={280}>

              <BarChart data={performanceData}>

                <XAxis
                  dataKey="name"
                  tickLine={false}
                  axisLine={false}
                />

                <YAxis
                  domain={[0, 100]}
                  tickLine={false}
                  axisLine={false}
                />

                <Tooltip
                  formatter={(value) =>
                    `${value.toFixed(2)}%`
                  }
                />

                <Bar
                  dataKey="value"
                  radius={[6, 6, 0, 0]}
                />

              </BarChart>

            </ResponsiveContainer>

          </div>

        </div>

      </div>


      {/* CONTROL PIPELINE */}

      <div className="dashboard-card pipeline-card">

        <div className="card-header">

          <div>

            <h2>Controller Pipeline</h2>

            <p>
              How a transaction moves from raw data to a controlled
              financial decision.
            </p>

          </div>

        </div>

        <div className="controller-pipeline">

          <div className="pipeline-step">

            <div className="pipeline-number">
              01
            </div>

            <strong>Ingest</strong>

            <span>
              Bank and ERP records enter the controller.
            </span>

          </div>

          <div className="pipeline-arrow">
            →
          </div>

          <div className="pipeline-step">

            <div className="pipeline-number">
              02
            </div>

            <strong>Reconcile</strong>

            <span>
              Deterministic rules identify likely matches.
            </span>

          </div>

          <div className="pipeline-arrow">
            →
          </div>

          <div className="pipeline-step">

            <div className="pipeline-number">
              03
            </div>

            <strong>Reason</strong>

            <span>
              AI analyzes ambiguous transactions.
            </span>

          </div>

          <div className="pipeline-arrow">
            →
          </div>

          <div className="pipeline-step pipeline-highlight">

            <div className="pipeline-number">
              04
            </div>

            <strong>Verify</strong>

            <span>
              Independent controls validate AI decisions.
            </span>

          </div>

          <div className="pipeline-arrow">
            →
          </div>

          <div className="pipeline-step">

            <div className="pipeline-number">
              05
            </div>

            <strong>Review</strong>

            <span>
              Humans resolve remaining uncertainty.
            </span>

          </div>

        </div>

      </div>


      {/* MEASURED RESULTS */}

      <div className="dashboard-card">

        <div className="card-header">

          <div>

            <h2>Controller Performance</h2>

            <p>
              Evaluation results from the current reconciliation batch.
            </p>

          </div>

        </div>

        <div className="performance-grid">

          <div className="performance-item">

            <span>
              Deterministic Accuracy
            </span>

            <strong>
              {metrics.deterministic_accuracy.toFixed(2)}%
            </strong>

            <small>
              Ground-truth invoice selection
            </small>

          </div>


          <div className="performance-item">

            <span>
              AI Cases
            </span>

            <strong>
              {metrics.ai_cases}
            </strong>

            <small>
              Uncertain cases sent to AI
            </small>

          </div>


          <div className="performance-item">

            <span>
              AI Recommendations
            </span>

            <strong>
              {metrics.ai_recommendations}
            </strong>

            <small>
              AI MATCH recommendations
            </small>

          </div>


          <div className="performance-item">

            <span>
              AI Match Rate
            </span>

            <strong>
              {metrics.ai_match_rate.toFixed(2)}%
            </strong>

            <small>
              AI MATCH recommendations among AI cases
            </small>

          </div>


          <div className="performance-item">

            <span>
              Guard Approved
            </span>

            <strong>
              {metrics.guard_approved}
            </strong>

            <small>
              AI matches independently verified
            </small>

          </div>


          <div className="performance-item">

            <span>
              AI Matches Blocked
            </span>

            <strong>
              {metrics.ai_matches_blocked}
            </strong>

            <small>
              Recommendations rejected by guard
            </small>

          </div>


          <div className="performance-item">

            <span>
              Guard Approval Accuracy
            </span>

            <strong>
              {metrics.guard_approval_accuracy.toFixed(2)}%
            </strong>

            <small>
              Correctness of approved AI matches
            </small>

          </div>


          <div className="performance-item">

            <span>
              Automated Match Rate
            </span>

            <strong>
              {metrics.final_match_rate.toFixed(2)}%
            </strong>

            <small>
              Transactions matched without human intervention
            </small>

          </div>

        </div>

      </div>


      {/* HUMAN REVIEW */}

      <div className="dashboard-card">

        <div className="card-header">

          <div>

            <h2>Human Review</h2>

            <p>
              Manual decisions made on transactions requiring human attention.
            </p>

          </div>

        </div>

        <div className="performance-grid">

          <div className="performance-item">

            <span>
              Reviewed
            </span>

            <strong>
              {metrics.human_reviewed ?? 0}
            </strong>

            <small>
              Transactions reviewed by a human
            </small>

          </div>


          <div className="performance-item">

            <span>
              Approved
            </span>

            <strong>
              {metrics.human_approved ?? 0}
            </strong>

            <small>
              Review decisions marked APPROVE
            </small>

          </div>


          <div className="performance-item">

            <span>
              Rejected
            </span>

            <strong>
              {metrics.human_rejected ?? 0}
            </strong>

            <small>
              Review decisions marked REJECT
            </small>

          </div>


          <div className="performance-item">

            <span>
              Unresolved
            </span>

            <strong>
              {metrics.human_unresolved ?? 0}
            </strong>

            <small>
              Cases left unresolved
            </small>

          </div>

        </div>

      </div>


      {/* PRINCIPLE */}

      <div className="dashboard-principle">

        <div className="principle-icon">
          ✓
        </div>

        <div>

          <span>
            CONTROL PRINCIPLE
          </span>

          <h3>
            AI recommends. Verification decides.
          </h3>

          <p>
            The system is designed around measured throughput,
            independent verification and an explicit exception list
            rather than blindly maximizing automation.
          </p>

        </div>

      </div>

    </div>
  );
}

export default Dashboard;