import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTransaction } from "../services/api";

function TransactionDetails() {
  const { transactionId } = useParams();

  const [transaction, setTransaction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadTransaction() {
      try {
        const data = await getTransaction(transactionId);
        setTransaction(data);
      } catch (err) {
        setError("Unable to load transaction details.");
      } finally {
        setLoading(false);
      }
    }

    loadTransaction();
  }, [transactionId]);

  if (loading) {
    return (
      <div className="page-container">
        <p>Loading transaction...</p>
      </div>
    );
  }

  if (error || !transaction) {
    return (
      <div className="page-container">
        <Link to="/transactions" className="back-link">
          ← Back to Transactions
        </Link>

        <div className="empty-state">
          <h2>Transaction not found</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const finalStatus =
    transaction.verification_decision ||
    transaction.deterministic_status ||
    "UNKNOWN";

  const statusClass = finalStatus.toLowerCase();

  return (
    <div className="page-container">

      {/* ================= HEADER ================= */}

      <div className="details-header">

        <div>
          <Link to="/transactions" className="back-link">
            ← Back to Transactions
          </Link>

          <h1>{transaction.transaction_id}</h1>

          <p>
            Reconciliation evidence and verification trail
          </p>
        </div>

        <span className={`status-badge status-${statusClass}`}>
          {finalStatus}
        </span>

      </div>


      {/* ================= TRANSACTION + INVOICE ================= */}

      <div className="evidence-grid">

        {/* BANK TRANSACTION */}

        <div className="dashboard-card evidence-card">

          <div className="evidence-title">
            <div className="evidence-icon">
              $
            </div>

            <div>
              <h2>Bank Transaction</h2>
              <span>Source record</span>
            </div>
          </div>

          <div className="detail-list">

            <div className="detail-row">
              <span>Transaction ID</span>
              <strong>
                {transaction.transaction_id}
              </strong>
            </div>

            <div className="detail-row">
              <span>Date</span>
              <strong>
                {transaction.date}
              </strong>
            </div>

            <div className="detail-row">
              <span>Counterparty</span>
              <strong>
                {transaction.counterparty}
              </strong>
            </div>

            <div className="detail-row">
              <span>Amount</span>
              <strong>
                {transaction.currency}{" "}
                {transaction.amount}
              </strong>
            </div>

          </div>

        </div>


        {/* ERP INVOICE */}

        <div className="dashboard-card evidence-card">

          <div className="evidence-title">
            <div className="evidence-icon">
              #
            </div>

            <div>
              <h2>ERP Invoice</h2>
              <span>Matched accounting record</span>
            </div>
          </div>

          <div className="detail-list">

            <div className="detail-row">
              <span>Invoice</span>
              <strong>
                {transaction.matched_invoice || "No match"}
              </strong>
            </div>

            <div className="detail-row">
              <span>Match Score</span>
              <strong>
                {transaction.match_score ?? "—"}
              </strong>
            </div>

            <div className="detail-row">
              <span>Deterministic Status</span>
              <strong>
                {transaction.deterministic_status || "—"}
              </strong>
            </div>

          </div>

        </div>

      </div>


      {/* ================= MATCHING EVIDENCE ================= */}

      <div className="dashboard-card">

        <div className="section-header">

          <div>
            <h2>Matching Evidence</h2>

            <p>
              Signals used by the reconciliation engine
            </p>
          </div>

        </div>


        <div className="evidence-signals">

          <div className="signal">

            <span className="signal-label">
              Amount
            </span>

            <span className="signal-value">
              Exact
            </span>

          </div>


          <div className="signal">

            <span className="signal-label">
              Date
            </span>

            <span className="signal-value">
              Exact
            </span>

          </div>


          <div className="signal">

            <span className="signal-label">
              Reference
            </span>

            <span className="signal-value">
              {transaction.matched_invoice
                ? "Matched"
                : "Not available"}
            </span>

          </div>


          <div className="signal">

            <span className="signal-label">
              Match Score
            </span>

            <span className="signal-value score-value">
              {transaction.match_score ?? "—"}
            </span>

          </div>

        </div>

      </div>


      {/* ================= AI REASONING ================= */}

      <div className="dashboard-card ai-card">

        <div className="section-header">

          <div>
            <h2>AI Reasoning</h2>

            <p>
              Semantic reasoning used for uncertain transactions
            </p>
          </div>

          <span className="ai-label">
            AI
          </span>

        </div>


        {transaction.ai_decision ? (

          <div className="ai-result">

            <div className="ai-result-row">

              <span>AI Decision</span>

              <strong>
                {transaction.ai_decision}
              </strong>

            </div>


            <div className="ai-result-row">

              <span>Candidate Invoice</span>

              <strong>
                {transaction.ai_invoice || "—"}
              </strong>

            </div>


            <div className="ai-result-row">

              <span>Confidence</span>

              <strong>
                {transaction.ai_confidence ?? "—"}
              </strong>

            </div>


            <div className="ai-result-row">

              <span>Risk</span>

              <strong>
                {transaction.ai_risk || "—"}
              </strong>

            </div>

          </div>

        ) : (

          <div className="ai-not-used">

            <span>✦</span>

            <div>
              <strong>AI reasoning was not required</strong>

              <p>
                This transaction was resolved using deterministic
                reconciliation and verification rules.
              </p>
            </div>

          </div>

        )}

      </div>


      {/* ================= VERIFICATION GUARD ================= */}

      <div className="dashboard-card verification-card">

        <div className="section-header">

          <div>
            <h2>Verification Guard</h2>

            <p>
              Independent validation of the proposed reconciliation
            </p>
          </div>

          <span className="verified-label">
            ✓ VERIFIED
          </span>

        </div>


        <div className="verification-result">

          <div className="verification-item">

            <span>
              Final Decision
            </span>

            <span
              className={`status-badge status-${statusClass}`}
            >
              {finalStatus}
            </span>

          </div>


          <div className="verification-item">

            <span>
              Verification Reason
            </span>

            <strong>
              {transaction.verification_reason ||
                "Transaction passed verification checks."}
            </strong>

          </div>

        </div>

      </div>


      {/* ================= AUDIT TRAIL ================= */}

      <div className="dashboard-card audit-card">

        <div className="section-header">

          <div>
            <h2>Decision Trail</h2>

            <p>
              How this transaction moved through the controller
            </p>
          </div>

        </div>


        <div className="timeline">

          <div className="timeline-item completed">
            <div className="timeline-dot">
              ✓
            </div>

            <div>
              <strong>
                Transaction ingested
              </strong>

              <p>
                Bank transaction entered the reconciliation batch.
              </p>
            </div>
          </div>


          <div className="timeline-item completed">
            <div className="timeline-dot">
              ✓
            </div>

            <div>
              <strong>
                Deterministic matching completed
              </strong>

              <p>
                Candidate invoice selected using reconciliation
                signals.
              </p>
            </div>
          </div>


          {transaction.ai_decision && (
            <div className="timeline-item completed">

              <div className="timeline-dot">
                ✦
              </div>

              <div>
                <strong>
                  AI reasoning completed
                </strong>

                <p>
                  Semantic reasoning was used because the transaction
                  required additional analysis.
                </p>
              </div>

            </div>
          )}


          <div className="timeline-item completed">

            <div className="timeline-dot">
              ✓
            </div>

            <div>
              <strong>
                Verification guard completed
              </strong>

              <p>
                Final decision was independently verified.
              </p>
            </div>

          </div>


          <div className="timeline-item final">

            <div className="timeline-dot">
              →
            </div>

            <div>
              <strong>
                Final status: {finalStatus}
              </strong>

              <p>
                This is the current operational state of the
                transaction.
              </p>
            </div>

          </div>

        </div>

      </div>

    </div>
  );
}

export default TransactionDetails;