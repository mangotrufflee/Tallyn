import { useEffect, useState } from "react";

import {
  Link,
} from "react-router-dom";

import {
  getAIInsights,
  getMetrics,
} from "../services/api";
import { hasGroundTruth } from "../utils/workflow";


function AIInsights() {

  const [transactions, setTransactions] =
    useState([]);

  const [metrics, setMetrics] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  // ========================================================
  // LOAD AI DATA
  // ========================================================

  useEffect(() => {

    async function loadAIInsights() {

      try {

        const [data, metricsData] = await Promise.all([
          getAIInsights(),
          getMetrics(),
        ]);

        setTransactions(data);
        setMetrics(metricsData);

      } catch (err) {

        console.error(err);

        setError(
          "Unable to load AI insights."
        );

      } finally {

        setLoading(false);
      }
    }


    loadAIInsights();

  }, []);


  // ========================================================
  // LOADING
  // ========================================================

  if (loading) {

    return (

      <div className="page-container">

        <div className="page-header">

          <div>

            <h1>
              AI Insights
            </h1>

            <p>
              AI-assisted reconciliation analysis
            </p>

          </div>

        </div>


        <div className="empty-state">

          <p>
            Loading AI analysis...
          </p>

        </div>

      </div>
    );
  }


  // ========================================================
  // ERROR
  // ========================================================

  if (error) {

    return (

      <div className="page-container">

        <div className="page-header">

          <div>

            <h1>
              AI Insights
            </h1>

            <p>
              AI-assisted reconciliation analysis
            </p>

          </div>

        </div>


        <div className="empty-state">

          <h2>
            Something went wrong
          </h2>

          <p>
            {error}
          </p>

        </div>

      </div>
    );
  }


  // ========================================================
  // CALCULATIONS
  // ========================================================

  const totalAI =
    transactions.length;


  const aiMatches =
    transactions.filter(
      transaction =>
        transaction.ai_decision === "MATCH"
    ).length;


  const aiReviews =
    transactions.filter(
      transaction =>
        transaction.ai_decision !== "MATCH"
    ).length;


  const guardApproved =
    transactions.filter(
      transaction =>
        transaction.ai_decision === "MATCH" &&
        transaction.verification_decision === "MATCHED"
    ).length;


  const guardBlocked =
    transactions.filter(
      transaction =>
        transaction.ai_decision === "MATCH" &&
        transaction.verification_decision !== "MATCHED"
    ).length;


  const aiMatchRate =
    totalAI > 0
      ? ((aiMatches / totalAI) * 100).toFixed(1)
      : "0.0";


  const guardApprovalRate =
    aiMatches > 0
      ? ((guardApproved / aiMatches) * 100).toFixed(1)
      : "0.0";


  // ========================================================
  // STATUS CLASS
  // ========================================================

  function getStatusClass(status) {

    if (status === "MATCHED") {
      return "matched";
    }

    if (status === "REVIEW") {
      return "review";
    }

    if (status === "EXCEPTION") {
      return "exception";
    }

    return "neutral";
  }


  // ========================================================
  // RENDER
  // ========================================================

  return (

    <div className="page-container">


      {/* ==================================================
          HEADER
      ================================================== */}

      <div className="page-header">

        <div>

          <h1>
            AI Insights
          </h1>

          <p>
            Understand how AI recommendations
            move through independent verification.
          </p>

        </div>


        <div className="ai-page-badge">

          ✦ Local AI Engine

        </div>

      </div>


      {/* ==================================================
          KPI CARDS
      ================================================== */}

      <div className="kpi-grid">


        <div className="kpi-card">

          <div className="kpi-top">

            <span className="kpi-title">
              AI Cases
            </span>

            <div className="kpi-icon neutral">
              ✦
            </div>

          </div>


          <div className="kpi-value">
            {totalAI}
          </div>


          <div className="kpi-footer neutral-text">
            Uncertain transactions sent to AI
          </div>

        </div>

        <div className="kpi-card">

          <div className="kpi-top">
            <span className="kpi-title">
              Recommendation Accuracy
            </span>
          </div>

          <div className="kpi-value">
            {hasGroundTruth(metrics) ? `${metrics.ai_recommendation_accuracy}%` : "—"}
          </div>

          <div className="kpi-footer neutral-text">
            {hasGroundTruth(metrics)
              ? "Accuracy among AI MATCH recommendations"
              : "Ground truth unavailable"}
          </div>

        </div>


        <div className="kpi-card">

          <div className="kpi-top">

            <span className="kpi-title">
              AI Matches
            </span>

            <div className="kpi-icon success">
              ✓
            </div>

          </div>


          <div className="kpi-value">
            {aiMatches}
          </div>


          <div className="kpi-footer success-text">
            {aiMatchRate}% of AI cases
          </div>

        </div>


        <div className="kpi-card">

          <div className="kpi-top">

            <span className="kpi-title">
              Guard Approved
            </span>

            <div className="kpi-icon success">
              ✓
            </div>

          </div>


          <div className="kpi-value">
            {guardApproved}
          </div>


          <div className="kpi-footer success-text">
            Safely promoted to MATCHED
          </div>

        </div>


        <div className="kpi-card">

          <div className="kpi-top">

            <span className="kpi-title">
              AI Matches Blocked
            </span>

            <div className="kpi-icon warning">
              !
            </div>

          </div>


          <div className="kpi-value">
            {guardBlocked}
          </div>


          <div className="kpi-footer warning-text">
            Prevented from auto-approval
          </div>

        </div>

      </div>


      {/* ==================================================
          PIPELINE
      ================================================== */}

      <div className="dashboard-card ai-pipeline-card">

        <div className="section-header">

          <div>

            <h2>
              AI → Verification Pipeline
            </h2>

            <p>
              Every AI recommendation is independently
              checked before becoming a final match.
            </p>

          </div>

        </div>


        <div className="ai-flow">


          <div className="ai-flow-step">

            <div className="ai-flow-number">
              {totalAI}
            </div>

            <strong>
              AI Cases
            </strong>

            <span>
              Uncertain transactions
            </span>

          </div>


          <div className="ai-flow-arrow">
            →
          </div>


          <div className="ai-flow-step">

            <div className="ai-flow-number">
              {aiMatches}
            </div>

            <strong>
              AI MATCH
            </strong>

            <span>
              Recommendations
            </span>

          </div>


          <div className="ai-flow-arrow">
            →
          </div>


          <div className="ai-flow-step">

            <div className="ai-flow-number">
              {guardApproved}
            </div>

            <strong>
              Guard Approved
            </strong>

            <span>
              Final MATCHED
            </span>

          </div>


          <div className="ai-flow-arrow blocked">
            /
          </div>


          <div className="ai-flow-step blocked-step">

            <div className="ai-flow-number">
              {guardBlocked}
            </div>

            <strong>
              Blocked
            </strong>

            <span>
              Sent to review
            </span>

          </div>

        </div>


        <div className="ai-principle">

          <span>
            ✓
          </span>

          <div>

            <strong>
              Verification-first principle
            </strong>

            <p>
              AI recommends. Deterministic rules
              verify. Humans resolve what remains
              uncertain.
            </p>

          </div>

        </div>

      </div>


      {/* ==================================================
          PERFORMANCE
      ================================================== */}

      <div className="dashboard-two-column">


        <div className="dashboard-card">

          <div className="section-header">

            <div>

              <h2>
                AI Recommendation Outcome
              </h2>

            </div>

          </div>


          <div className="ai-outcome-chart">


            <div className="outcome-row">

              <div className="outcome-label">

                <span>
                  AI MATCH
                </span>

                <strong>
                  {aiMatches}
                </strong>

              </div>


              <div className="outcome-bar">

                <div
                  className="outcome-fill ai-match-fill"
                  style={{
                    width: `${aiMatchRate}%`,
                  }}
                />

              </div>

            </div>


            <div className="outcome-row">

              <div className="outcome-label">

                <span>
                  AI REVIEW
                </span>

                <strong>
                  {aiReviews}
                </strong>

              </div>


              <div className="outcome-bar">

                <div
                  className="outcome-fill ai-review-fill"
                  style={{
                    width:
                      `${totalAI > 0
                        ? (aiReviews / totalAI) * 100
                        : 0}%`,
                  }}
                />

              </div>

            </div>

          </div>

        </div>


        <div className="dashboard-card">

          <div className="section-header">

            <div>

              <h2>
                Verification Outcome
              </h2>

            </div>

          </div>


          <div className="verification-stat">

            <div>

              <span>
                Guard approval rate
              </span>

              <strong>
                {guardApprovalRate}%
              </strong>

            </div>


            <div className="verification-stat-bar">

              <div
                style={{
                  width:
                    `${guardApprovalRate}%`,
                }}
              />

            </div>


            <p>
              Percentage of AI MATCH recommendations
              that passed independent verification.
            </p>

          </div>

        </div>

      </div>


      {/* ==================================================
          AI CASE TABLE
      ================================================== */}

      <div className="dashboard-card ai-table-card">

        <div className="section-header">

          <div>

            <h2>
              AI Cases
            </h2>

            <p>
              Transaction-level AI recommendations
              and verification outcomes.
            </p>

          </div>

          <span className="table-count">

            {totalAI} cases

          </span>

        </div>


        {
          transactions.length === 0 ? (

            <div className="empty-state">

              <h3>
                No AI cases
              </h3>

              <p>
                No transactions have been processed
                by the AI engine yet.
              </p>

            </div>

          ) : (

            <div className="table-wrapper">

              <table className="transaction-table">

                <thead>

                  <tr>

                    <th>
                      Transaction
                    </th>

                    <th>
                      Counterparty
                    </th>

                    <th>
                      Amount
                    </th>

                    <th>
                      AI Decision
                    </th>

                    <th>
                      AI Invoice
                    </th>

                    <th>
                      Confidence
                    </th>

                    <th>
                      Risk
                    </th>

                    <th>
                      Guard
                    </th>

                    <th>
                      View
                    </th>

                  </tr>

                </thead>


                <tbody>

                  {
                    transactions.map(
                      transaction => (

                        <tr
                          key={
                            transaction.transaction_id
                          }
                        >

                          <td>

                            <strong>
                              {
                                transaction.transaction_id
                              }
                            </strong>

                          </td>


                          <td>
                            {
                              transaction.counterparty
                            }
                          </td>


                          <td>
                            {
                              transaction.currency
                            }{" "}
                            {
                              transaction.amount
                            }
                          </td>


                          <td>

                            <span className="status-badge status-review">

                              {
                                transaction.ai_decision
                              }

                            </span>

                          </td>


                          <td>

                            {
                              transaction.ai_invoice ||
                              "—"
                            }

                          </td>


                          <td>

                            {
                              transaction.ai_confidence ??
                              "—"
                            }

                          </td>


                          <td>

                            <span
                              className={
                                `risk-badge risk-${(
                                  transaction.ai_risk ||
                                  "unknown"
                                ).toLowerCase()}`
                              }
                            >

                              {
                                transaction.ai_risk ||
                                "—"
                              }

                            </span>

                          </td>


                          <td>

                            <span
                              className={
                                `status-badge status-${getStatusClass(
                                  transaction.verification_decision
                                )}`
                              }
                            >

                              {
                                transaction.verification_decision ||
                                "—"
                              }

                            </span>

                          </td>


                          <td>

                            <Link
                              to={
                                `/transactions/${transaction.transaction_id}`
                              }
                              className="view-link"
                            >
                              View
                            </Link>

                          </td>

                        </tr>

                      )
                    )
                  }

                </tbody>

              </table>

            </div>
          )
        }

      </div>


      {/* ==================================================
          HONEST AI NOTE
      ================================================== */}

      <div className="dashboard-card ai-note-card">

        <div className="ai-note-icon">
          !
        </div>

        <div>

          <h3>
            AI is advisory, not authoritative
          </h3>

          <p>
            The AI model does not directly change
            accounting records. Its recommendation
            must pass the independent verification
            guard before it can become a MATCHED
            transaction.
          </p>

        </div>

      </div>

    </div>
  );
}


export default AIInsights;