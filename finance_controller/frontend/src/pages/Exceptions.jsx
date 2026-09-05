import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import WorkflowProgress from "../components/WorkflowProgress";
import { getExceptions } from "../services/api";
import { formatAmount } from "../utils/workflow";

function exceptionType(item) {
  if (item.verification_decision === "EXCEPTION") return "Exception";
  if (item.verification_decision === "REVIEW") return "Needs review";
  return item.verification_decision || "Open";
}

export default function Exceptions() {
  const [exceptions, setExceptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadExceptions() {
      try {
        const data = await getExceptions();
        setExceptions(data);
      } catch {
        setError("Unable to load exceptions.");
      } finally {
        setLoading(false);
      }
    }
    loadExceptions();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <h1>Exceptions</h1>
        <p>Loading exceptions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <h1>Exceptions</h1>
        <div className="empty-state">
          <h2>Something went wrong</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Exceptions</h1>
          <p>Actionable queue of transactions that still need a human decision.</p>
        </div>
        <div className="exception-count">{exceptions.length} Open</div>
      </div>

      <WorkflowProgress
        currentStep={exceptions.length ? 4 : 5}
        hint={exceptions.length ? "Open an item to review evidence and decide." : "No open exceptions."}
      />

      <div className="exception-summary">
        <div className="summary-box">
          <span>Total open</span>
          <strong>{exceptions.length}</strong>
        </div>
        <div className="summary-box">
          <span>Needs review</span>
          <strong>{exceptions.filter((item) => item.verification_decision === "REVIEW").length}</strong>
        </div>
        <div className="summary-box">
          <span>Exceptions</span>
          <strong>{exceptions.filter((item) => item.verification_decision === "EXCEPTION").length}</strong>
        </div>
      </div>

      <div className="dashboard-card exception-card">
        <div className="section-header">
          <div>
            <h2>Review Queue</h2>
            <p>Click an exception to open verification and evidence.</p>
          </div>
        </div>

        {exceptions.length === 0 ? (
          <div className="empty-state">
            <h2>No exceptions</h2>
            <p>All transactions have been resolved.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="transaction-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Transaction</th>
                  <th>Amount</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {exceptions.map((transaction) => {
                  const status = transaction.verification_decision || "UNKNOWN";
                  return (
                    <tr key={transaction.transaction_id}>
                      <td>{exceptionType(transaction)}</td>
                      <td>
                        <strong>{transaction.transaction_id}</strong>
                        <span className="invoice-subtext">{transaction.counterparty || "—"}</span>
                      </td>
                      <td><strong>{formatAmount(transaction)}</strong></td>
                      <td className="reason-cell">
                        {transaction.verification_reason || transaction.reason || "Requires manual verification"}
                      </td>
                      <td>
                        <span className={`status-badge status-${status.toLowerCase()}`}>{status}</span>
                      </td>
                      <td>
                        <Link
                          to={`/verification?transactionId=${encodeURIComponent(transaction.transaction_id)}`}
                          className="view-link"
                        >
                          Verify →
                        </Link>
                        {" "}
                        <Link
                          to={`/transactions/${transaction.transaction_id}`}
                          className="view-link"
                        >
                          Details →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
