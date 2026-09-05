import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import "../App.css";
import WorkflowProgress from "../components/WorkflowProgress";
import { getTransactions } from "../services/api";

function getFinalStatus(transaction) {
  if (transaction.verification_decision) {
    return transaction.verification_decision;
  }

  return transaction.deterministic_status;
}

function getStatusClass(status) {
  switch (status) {
    case "MATCHED":
      return "status-matched";

    case "REVIEW":
      return "status-review";

    case "EXCEPTION":
      return "status-exception";

    default:
      return "status-neutral";
  }
}

function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [aiFilter, setAiFilter] = useState("ALL");
  const [error, setError] = useState(null);

  useEffect(() => {
    getTransactions()
      .then((data) => {
        setTransactions(
          Array.isArray(data)
            ? data
            : data.transactions || []
        );
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);

  const filteredTransactions = transactions.filter(
    (transaction) => {
      const finalStatus = getFinalStatus(transaction);

      const searchText = search.toLowerCase();

      const matchesSearch =
        transaction.transaction_id
          ?.toLowerCase()
          .includes(searchText) ||
        transaction.counterparty
          ?.toLowerCase()
          .includes(searchText) ||
        transaction.matched_invoice
          ?.toLowerCase()
          .includes(searchText);

      const matchesStatus =
        statusFilter === "ALL" ||
        finalStatus === statusFilter;

      const aiProcessed =
        transaction.ai_decision !== null;

      const matchesAI =
        aiFilter === "ALL" ||
        (aiFilter === "PROCESSED" && aiProcessed) ||
        (aiFilter === "NOT_PROCESSED" && !aiProcessed);

      return (
        matchesSearch &&
        matchesStatus &&
        matchesAI
      );
    }
  );

 return (
  <>
    {/* Header */}
    <header className="topbar">
      <div>
        <h1>Transactions</h1>

        <p>
          Results for the current reconciliation batch
        </p>
      </div>
    </header>
    <WorkflowProgress currentStep={4} hint="Open a transaction to see its full decision story." />

    {/* Error */}
    {error && (
      <div className="dashboard-card error-box">
        Unable to load transactions: {error}
      </div>
    )}

    {/* Transactions */}
    {!error && (
      <div className="dashboard-card transaction-card">

        {/* Table Header */}
        <div className="table-header">
          <div>
            <h2>All Transactions</h2>

            <p>
              Showing{" "}
              <strong>
                {filteredTransactions.length}
              </strong>{" "}
              of {transactions.length} records
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="transaction-filters">

          <div className="search-box">
            <span>⌕</span>

            <input
              type="text"
              placeholder="Search transaction, vendor or invoice..."
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
            />
          </div>

          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value)
            }
          >
            <option value="ALL">
              All Statuses
            </option>

            <option value="MATCHED">
              Matched
            </option>

            <option value="REVIEW">
              Review
            </option>

            <option value="EXCEPTION">
              Exception
            </option>
          </select>

          <select
            value={aiFilter}
            onChange={(event) =>
              setAiFilter(event.target.value)
            }
          >
            <option value="ALL">
              AI: All
            </option>

            <option value="PROCESSED">
              AI Processed
            </option>

            <option value="NOT_PROCESSED">
              AI Not Processed
            </option>
          </select>

        </div>

        {/* Table */}
        {filteredTransactions.length > 0 ? (

          <div className="table-wrapper">

            <table className="transaction-table">

              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Date</th>
                  <th>Counterparty</th>
                  <th>Amount</th>
                  <th>Currency</th>
                  <th>Matched Invoice</th>
                  <th>Score</th>
                  <th>Deterministic</th>
                  <th>AI Decision</th>
                  <th>Verification</th>
                  <th>Review</th>
                  <th>View</th>
                </tr>
              </thead>

              <tbody>
                {filteredTransactions.map((transaction) => {

                  return (
                    <tr key={transaction.transaction_id}>

                      {/* Transaction */}
                      <td>
                        <strong>
                          {transaction.transaction_id}
                        </strong>

                        <span className="invoice-subtext">
                          {transaction.matched_invoice || "No invoice"}
                        </span>
                      </td>

                      {/* Date */}
                      <td>
                        {new Date(transaction.date).toLocaleDateString(
                          "en-IN",
                          {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                          }
                        )}
                      </td>

                      {/* Counterparty */}
                      <td>
                        {transaction.counterparty}
                      </td>

                      {/* Amount */}
                      <td>
                        <strong>
                          {transaction.currency === "INR"
                            ? "₹"
                            : transaction.currency}

                          {Number(transaction.amount).toLocaleString("en-IN")}
                        </strong>
                      </td>

                      {/* Currency */}
                      <td>
                        {transaction.currency || "—"}
                      </td>

                      {/* Matched Invoice */}
                      <td>
                        {transaction.matched_invoice || "—"}
                      </td>

                      {/* Score */}
                      <td>
                        <span
                          className={
                            transaction.match_score >= 90
                              ? "score-high"
                              : transaction.match_score >= 70
                              ? "score-medium"
                              : "score-low"
                          }
                        >
                          {transaction.match_score ?? "—"}
                        </span>
                      </td>

                      {/* Deterministic */}
                      <td>
                        <span
                          className={`status-badge ${getStatusClass(
                            transaction.deterministic_status
                          )}`}
                        >
                          {transaction.deterministic_status || "—"}
                        </span>
                      </td>

                      {/* AI Decision */}
                      <td>
                        {transaction.ai_decision || "—"}
                      </td>

                      {/* Verification */}
                      <td>
                        <span
                          className={`status-badge ${getStatusClass(
                            transaction.verification_decision
                          )}`}
                        >
                          {transaction.verification_decision || "—"}
                        </span>
                      </td>

                      {/* Review */}
                      <td>
                        {transaction.review_status === "COMPLETED"
                          ? transaction.review_decision
                          : "Open"}
                      </td>

                      {/* View */}
                      <td>
                        <Link
                          to={`/transactions/${transaction.transaction_id}`}
                          className="view-link"
                        >
                          View →
                        </Link>
                      </td>

                    </tr>
                  );
                })}
              </tbody>

            </table>

          </div>

        ) : (

          <div className="empty-state">

            <div className="empty-icon">
              ⌕
            </div>

            <h3>
              No transactions found
            </h3>

            <p>
              Try changing your search or filters.
            </p>

          </div>

        )}

      </div>
    )}
  </>
);
}

export default Transactions;