import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getVerification } from "../services/api";

function Verification() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadVerification() {
      try {
        const data = await getVerification();
        setRecords(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadVerification();
  }, []);

  const stats = useMemo(() => {
    const verified = records.filter(
      (record) => record.verification_decision
    );

    const passed = verified.filter(
      (record) => record.verification_decision === "MATCHED"
    ).length;

    const review = verified.filter(
      (record) => record.verification_decision === "REVIEW"
    ).length;

    const exceptions = verified.filter(
      (record) => record.verification_decision === "EXCEPTION"
    ).length;

    const aiMatches = records.filter(
      (record) => record.ai_decision === "MATCH"
    ).length;

    const guardApproved = records.filter(
      (record) =>
        record.ai_decision === "MATCH" &&
        record.verification_decision === "MATCHED"
    ).length;

    const blocked = records.filter(
      (record) =>
        record.ai_decision === "MATCH" &&
        record.verification_decision !== "MATCHED"
    ).length;

    return {
      total: records.length,
      verified: verified.length,
      passed,
      review,
      exceptions,
      aiMatches,
      guardApproved,
      blocked,
    };
  }, [records]);

  if (loading) {
    return (
      <div className="verification-page">
        <div className="page-loading">Loading verification data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="verification-page">
        <div className="page-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="verification-page">

      {/* HEADER */}
      <div className="page-header">
        <div>
          <div className="verification-badge">
            VERIFICATION LAYER
          </div>

          <h1>Verification Guard</h1>

          <p>
            Independent checks that validate AI recommendations
            before they become final reconciliation decisions.
          </p>
        </div>
      </div>

      {/* KPI CARDS */}
      <div className="verification-kpis">

        <div className="verification-kpi">
          <span>Total Records</span>
          <strong>{stats.total}</strong>
          <small>Transactions evaluated</small>
        </div>

        <div className="verification-kpi">
          <span>Verified</span>
          <strong>{stats.verified}</strong>
          <small>Records with guard decisions</small>
        </div>

        <div className="verification-kpi">
          <span>Guard Approved</span>
          <strong>{stats.guardApproved}</strong>
          <small>AI matches independently verified</small>
        </div>

        <div className="verification-kpi">
          <span>AI Matches Blocked</span>
          <strong>{stats.blocked}</strong>
          <small>AI recommendations stopped</small>
        </div>

      </div>

      {/* PIPELINE */}
      <div className="verification-card">

        <div className="section-heading">
          <div>
            <h2>Verification Pipeline</h2>
            <p>
              AI recommendations pass through an independent
              verification layer before becoming trusted matches.
            </p>
          </div>
        </div>

        <div className="verification-flow">

          <div className="verification-flow-step">
            <div className="verification-flow-number">01</div>
            <strong>Deterministic Match</strong>
            <span>
              Rules-based candidate selection
            </span>
          </div>

          <div className="verification-arrow">→</div>

          <div className="verification-flow-step">
            <div className="verification-flow-number">02</div>
            <strong>AI Reasoning</strong>
            <span>
              Semantic analysis of uncertain cases
            </span>
          </div>

          <div className="verification-arrow">→</div>

          <div className="verification-flow-step verification-highlight">
            <div className="verification-flow-number">03</div>
            <strong>Verification Guard</strong>
            <span>
              Independent consistency checks
            </span>
          </div>

          <div className="verification-arrow">→</div>

          <div className="verification-flow-step">
            <div className="verification-flow-number">04</div>
            <strong>Final Decision</strong>
            <span>
              Match, review or exception
            </span>
          </div>

        </div>
      </div>

      {/* OUTCOME SUMMARY */}
      <div className="verification-grid">

        <div className="verification-card">
          <div className="section-heading">
            <div>
              <h2>Guard Outcomes</h2>
              <p>Final decisions produced by the verification layer.</p>
            </div>
          </div>

          <div className="verification-bars">

            <div className="verification-bar-row">
              <div className="verification-bar-label">
                <span>Verified Match</span>
                <strong>{stats.passed}</strong>
              </div>

              <div className="verification-bar">
                <div
                  className="verification-bar-fill"
                  style={{
                    width: `${
                      stats.verified
                        ? (stats.passed / stats.verified) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <div className="verification-bar-row">
              <div className="verification-bar-label">
                <span>Review</span>
                <strong>{stats.review}</strong>
              </div>

              <div className="verification-bar">
                <div
                  className="verification-bar-fill"
                  style={{
                    width: `${
                      stats.verified
                        ? (stats.review / stats.verified) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <div className="verification-bar-row">
              <div className="verification-bar-label">
                <span>Exception</span>
                <strong>{stats.exceptions}</strong>
              </div>

              <div className="verification-bar">
                <div
                  className="verification-bar-fill"
                  style={{
                    width: `${
                      stats.verified
                        ? (stats.exceptions / stats.verified) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

          </div>
        </div>

        {/* PRINCIPLE CARD */}
        <div className="verification-card verification-principle">

          <div className="verification-principle-icon">
            ✓
          </div>

          <div>
            <span className="verification-label">
              CONTROL PRINCIPLE
            </span>

            <h2>AI recommends. Verification decides.</h2>

            <p>
              The AI model is intentionally advisory. A recommendation
              can only become a trusted match when the verification
              layer independently validates it.
            </p>
          </div>

        </div>

      </div>

      {/* VERIFICATION TABLE */}
      <div className="verification-card">

        <div className="section-heading">
          <div>
            <h2>Verification Records</h2>
            <p>
              Detailed evidence behind each AI-assisted verification.
            </p>
          </div>

          <span className="table-count">
            {records.length} records
          </span>
        </div>

        <div className="verification-table-wrapper">

          <table className="verification-table">

            <thead>
              <tr>
                <th>Transaction</th>
                <th>AI Decision</th>
                <th>AI Confidence</th>
                <th>Risk</th>
                <th>Guard Decision</th>
                <th>Checks</th>
                <th></th>
              </tr>
            </thead>

            <tbody>

              {records
                .filter((record) => record.ai_decision)
                .map((record) => {

                  const checks =
                    record.verification_checks || {};

                  const checkEntries =
                    Object.entries(checks);

                  return (
                    <tr key={record.transaction_id}>

                      <td>
                        <div className="verification-transaction">
                          <strong>
                            {record.transaction_id}
                          </strong>

                          <span>
                            {record.counterparty}
                          </span>
                        </div>
                      </td>

                      <td>
                        <span
                          className={`verification-decision ${
                            record.ai_decision === "MATCH"
                              ? "decision-match"
                              : "decision-review"
                          }`}
                        >
                          {record.ai_decision}
                        </span>
                      </td>

                      <td>
                        {record.ai_confidence
                          ? `${(
                              Number(record.ai_confidence) * 100
                            ).toFixed(0)}%`
                          : "—"}
                      </td>

                      <td>
                        <span
                          className={`risk-badge ${
                            record.ai_risk === "LOW"
                              ? "risk-low"
                              : record.ai_risk === "MEDIUM"
                              ? "risk-medium"
                              : record.ai_risk === "HIGH"
                              ? "risk-high"
                              : "risk-unknown"
                          }`}
                        >
                          {record.ai_risk || "UNKNOWN"}
                        </span>
                      </td>

                      <td>
                        <span
                          className={`verification-decision ${
                            record.verification_decision === "MATCHED"
                              ? "decision-match"
                              : record.verification_decision === "REVIEW"
                              ? "decision-review"
                              : "decision-exception"
                          }`}
                        >
                          {record.verification_decision || "PENDING"}
                        </span>
                      </td>

                      <td>
                        <div className="check-list">

                          {checkEntries.length > 0 ? (
                            checkEntries.map(([key, value]) => (
                              <span
                                key={key}
                                className={
                                  value === true
                                    ? "check-pass"
                                    : value === false
                                    ? "check-fail"
                                    : "check-neutral"
                                }
                              >
                                {value === true
                                  ? "✓"
                                  : value === false
                                  ? "×"
                                  : "•"}{" "}
                                {key.replaceAll("_", " ")}
                              </span>
                            ))
                          ) : (
                            <span className="check-neutral">
                              No checks available
                            </span>
                          )}

                        </div>
                      </td>

                      <td>
                        <Link
                          to={`/transactions/${record.transaction_id}`}
                          className="verification-view"
                        >
                          View
                        </Link>
                      </td>

                    </tr>
                  );
                })}

            </tbody>

          </table>

        </div>
      </div>

    </div>
  );
}

export default Verification;