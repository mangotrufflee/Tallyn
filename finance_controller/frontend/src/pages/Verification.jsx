import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import WorkflowProgress from "../components/WorkflowProgress";
import { getVerification, reviewTransaction } from "../services/api";
import { formatAmount, formatDate, parseChecks } from "../utils/workflow";

function isPending(record) {
  return (
    record.review_status !== "COMPLETED" &&
    (record.verification_decision === "REVIEW" ||
      record.verification_decision === "EXCEPTION")
  );
}

export default function Verification() {
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get("transactionId");
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState("");
  const [message, setMessage] = useState("");

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

  useEffect(() => {
    if (!focusId) return;
    const node = document.getElementById(`item-${focusId}`);
    if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, records]);

  const pending = useMemo(() => records.filter(isPending), [records]);
  const stats = useMemo(() => {
    const guardApproved = records.filter(
      (record) => record.ai_decision === "MATCH" && record.verification_decision === "MATCHED"
    ).length;
    const blocked = records.filter(
      (record) => record.ai_decision === "MATCH" && record.verification_decision !== "MATCHED"
    ).length;
    return { total: records.length, pending: pending.length, guardApproved, blocked };
  }, [records, pending.length]);

  async function submitReview(transactionId, decision) {
    const note = notes[transactionId] || "";
    if ((decision === "REJECT" || decision === "UNRESOLVED") && !note.trim()) {
      setMessage("Add a comment before rejecting or keeping an exception.");
      return;
    }
    setBusyId(transactionId);
    setMessage("");
    try {
      await reviewTransaction(transactionId, decision, note);
      const data = await getVerification();
      setRecords(data);
      setNotes((current) => ({ ...current, [transactionId]: "" }));
      setMessage(`Decision saved for ${transactionId}.`);
    } catch (err) {
      setMessage(err.message || "Unable to submit review.");
    } finally {
      setBusyId("");
    }
  }

  if (loading) {
    return (
      <div className="verification-page">
        <div className="page-loading">Loading verification queue...</div>
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
      <div className="page-header">
        <div>
          <div className="verification-badge">HUMAN WORK QUEUE</div>
          <h1>Verification</h1>
          <p>Unresolved transactions after AI recommendation and Verification Guard. Decide each item, then it leaves this queue.</p>
        </div>
      </div>

      <WorkflowProgress
        currentStep={pending.length ? 4 : 5}
        hint={pending.length ? `${pending.length} items waiting for a human decision.` : "Queue is clear."}
      />

      <div className="verification-kpis">
        <div className="verification-kpi"><span>Pending</span><strong>{stats.pending}</strong><small>Need a human decision</small></div>
        <div className="verification-kpi"><span>Guard Approved</span><strong>{stats.guardApproved}</strong><small>AI matches independently verified</small></div>
        <div className="verification-kpi"><span>Guard Rejected</span><strong>{stats.blocked}</strong><small>AI matches blocked</small></div>
        <div className="verification-kpi"><span>All records</span><strong>{stats.total}</strong><small>In the current batch</small></div>
      </div>

      {message && <div className="review-message">{message}</div>}

      <div className="verification-card">
        <div className="section-heading">
          <div>
            <h2>Pending decisions</h2>
            <p>Approve the match, reject it, or keep it as an exception.</p>
          </div>
          <span className="table-count">{pending.length} open</span>
        </div>

        {pending.length === 0 ? (
          <div className="empty-state">
            <h2>No pending verification items</h2>
            <p>Human review is complete for the current batch.</p>
          </div>
        ) : (
          <div className="queue-list">
            {pending.map((record) => {
              const checks = parseChecks(record.verification_checks);
              const focused = record.transaction_id === focusId;
              return (
                <article
                  key={record.transaction_id}
                  className={`queue-card ${focused ? "is-focused" : ""}`}
                  id={`item-${record.transaction_id}`}
                >
                  <div className="queue-card-top">
                    <div>
                      <strong>{record.transaction_id}</strong>
                      <span>{record.counterparty || "—"}</span>
                    </div>
                    <span className={`status-badge status-${(record.verification_decision || "review").toLowerCase()}`}>
                      {record.verification_decision}
                    </span>
                  </div>
                  <div className="queue-meta">
                    <span>Amount <strong>{formatAmount(record)}</strong></span>
                    <span>Date <strong>{formatDate(record.date)}</strong></span>
                    <span>AI <strong>{record.ai_decision || "—"}</strong></span>
                    <span>Confidence <strong>{
                      record.ai_confidence == null
                        ? "—"
                        : Number(record.ai_confidence) <= 1
                          ? `${Math.round(Number(record.ai_confidence) * 100)}%`
                          : `${record.ai_confidence}%`
                    }</strong></span>
                    <span>Guard <strong>{record.verification_decision || "—"}</strong></span>
                  </div>
                  {record.ai_reason && <p className="queue-reason">{record.ai_reason}</p>}
                  {record.verification_reason && <p className="queue-reason">{record.verification_reason}</p>}
                  {Object.keys(checks).length > 0 && (
                    <div className="check-list check-list-inline">
                      {Object.entries(checks).map(([key, value]) => (
                        <span key={key} className={value === true ? "check-pass" : value === false ? "check-fail" : "check-neutral"}>
                          {value === true ? "✓" : value === false ? "×" : "•"} {key.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                  )}
                  <textarea
                    className="review-note"
                    placeholder="Comment required for reject or keep as exception"
                    value={notes[record.transaction_id] || ""}
                    onChange={(event) =>
                      setNotes((current) => ({ ...current, [record.transaction_id]: event.target.value }))
                    }
                  />
                  <div className="review-actions">
                    <button className="review-button approve" disabled={busyId === record.transaction_id} onClick={() => submitReview(record.transaction_id, "APPROVE")}>
                      Approve Match
                    </button>
                    <button className="review-button reject" disabled={busyId === record.transaction_id} onClick={() => submitReview(record.transaction_id, "REJECT")}>
                      Reject Match
                    </button>
                    <button className="review-button unresolved" disabled={busyId === record.transaction_id} onClick={() => submitReview(record.transaction_id, "UNRESOLVED")}>
                      Keep as Exception
                    </button>
                    <Link className="verification-view" to={`/transactions/${record.transaction_id}`}>
                      Open evidence →
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
