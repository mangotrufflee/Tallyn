import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getExceptions } from "../services/api";

function Exceptions() {
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

      {/* Header */}
      <div className="page-header">
        <div>
          <h1>Exceptions</h1>
          <p>
            Transactions that require human review or could not be resolved
          </p>
        </div>

        <div className="exception-count">
          {exceptions.length} Open
        </div>
      </div>

      {/* Summary */}
      <div className="exception-summary">

        <div className="summary-box">
          <span>Total Exceptions</span>
          <strong>{exceptions.length}</strong>
        </div>

        <div className="summary-box">
          <span>Requires Review</span>
          <strong>
            {
              exceptions.filter(
                (item) =>
                  item.verification_decision === "REVIEW"
              ).length
            }
          </strong>
        </div>

        <div className="summary-box">
          <span>Unresolved</span>
          <strong>
            {
              exceptions.filter(
                (item) =>
                  item.verification_decision === "EXCEPTION"
              ).length
            }
          </strong>
        </div>

      </div>

      {/* Exception Table */}
      <div className="dashboard-card exception-card">

        <div className="section-header">
          <div>
            <h2>Review Queue</h2>
            <p>
              Review transactions where automated verification was not
              sufficient
            </p>
          </div>
        </div>

        {exceptions.length === 0 ? (
          <div className="empty-state">
            <h2>No exceptions</h2>
            <p>All transactions have been successfully resolved.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="transaction-table">

              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Counterparty</th>
                  <th>Amount</th>
                  <th>Invoice</th>
                  <th>AI Decision</th>
                  <th>Verification</th>
                  <th>Review</th>
                  <th>Score</th>
                  <th>Decision</th>
                  <th>Reason</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {exceptions.map((transaction) => {

                  const status =
                    transaction.verification_decision ||
                    transaction.deterministic_status ||
                    "UNKNOWN";

                  return (
                    <tr key={transaction.transaction_id}>

                      <td>
                        {transaction.ai_decision || "—"}
                      </td>

                      <td>
                        {transaction.verification_decision || "—"}
                      </td>

                      <td>
                        {transaction.review_status === "COMPLETED"
                          ? transaction.review_decision
                          : "Open"}
                      </td>

                      <td>
                        <strong>
                          {transaction.transaction_id}
                        </strong>
                      </td>

                      <td>
                        {transaction.counterparty}
                      </td>

                      <td>
                        {transaction.currency}{" "}
                        {transaction.amount}
                      </td>

                      <td>
                        {transaction.matched_invoice || "—"}
                      </td>

                      <td>
                        {transaction.match_score ?? "—"}
                      </td>

                      <td>
                        <span
                          className={`status-badge status-${status.toLowerCase()}`}
                        >
                          {status}
                        </span>
                      </td>

                      <td className="reason-cell">
                        {transaction.verification_reason ||
                          "Requires manual verification"}
                      </td>

                      <td>
                        <Link
                          to={`/transactions/${transaction.transaction_id}`}
                          className="view-link"
                        >
                          Review →
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

export default Exceptions;