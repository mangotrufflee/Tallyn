import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import WorkflowProgress from "../components/WorkflowProgress";
import { getTransaction, reviewTransaction } from "../services/api";
import { formatAmount, formatDate, parseChecks } from "../utils/workflow";

function OriginalFields({ title, fields }) {
  const entries = Object.entries(fields || {});
  return (
    <div className="dashboard-card original-fields-card">
      <div className="section-header">
        <div>
          <h2>{title}</h2>
          <p>Original uploaded record fields retained for audit.</p>
        </div>
        <span className="table-count">{entries.length} fields</span>
      </div>
      {entries.length === 0 ? (
        <p className="muted-note">No original fields available.</p>
      ) : (
        <div className="original-fields-grid">
          {entries.map(([key, value]) => (
            <div className="original-field" key={key}>
              <span>{key.replaceAll("_", " ")}</span>
              <strong>{String(value ?? "—")}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StoryCard({ step, title, kicker, children }) {
  return (
    <div className="dashboard-card story-card">
      <div className="story-kicker">{step} — {kicker}</div>
      <h2>{title}</h2>
      {children}
    </div>
  );
}

function formatConfidence(value) {
  if (value == null || value === "") return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  if (number <= 1) return `${Math.round(number * 100)}%`;
  return `${number}%`;
}

export default function TransactionDetails() {
  const { transactionId } = useParams();
  const [transaction, setTransaction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");

  useEffect(() => {
    async function loadTransaction() {
      try {
        const data = await getTransaction(transactionId);
        setTransaction(data);
      } catch {
        setError("Unable to load transaction details.");
      } finally {
        setLoading(false);
      }
    }
    loadTransaction();
  }, [transactionId]);

  async function handleReview(decision) {
    if ((decision === "REJECT" || decision === "UNRESOLVED") && !reviewNote.trim()) {
      setReviewMessage("Add a comment before rejecting or keeping this as an exception.");
      return;
    }
    setReviewing(true);
    setReviewMessage("");
    try {
      await reviewTransaction(transactionId, decision, reviewNote);
      const updated = await getTransaction(transactionId);
      setTransaction(updated);
      setReviewNote("");
      setReviewMessage(`Decision saved: ${decision}.`);
    } catch (err) {
      setReviewMessage(err.message || "Unable to submit review.");
    } finally {
      setReviewing(false);
    }
  }

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
        <Link to="/transactions" className="back-link">← Back to Transactions</Link>
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
  const needsReview =
    transaction.review_status !== "COMPLETED" &&
    (finalStatus === "REVIEW" || finalStatus === "EXCEPTION");
  const checks = parseChecks(transaction.verification_checks);
  const workflowStep = transaction.review_status === "COMPLETED" || !needsReview ? 5 : 4;

  return (
    <div className="page-container">
      <div className="details-header">
        <div>
          <Link to="/exceptions" className="back-link">← Back to Exceptions</Link>
          <h1>{transaction.transaction_id}</h1>
          <p>Complete decision story from source data to final status.</p>
        </div>
        <span className={`status-badge status-${finalStatus.toLowerCase()}`}>{finalStatus}</span>
      </div>

      <WorkflowProgress
        currentStep={workflowStep}
        hint={needsReview ? "This item still needs a human decision." : "This transaction has a final recorded status."}
      />

      <StoryCard step="01" kicker="SOURCE DATA" title="Bank and supporting records">
        <div className="evidence-grid">
          <div>
            <h3>Bank Transaction</h3>
            <div className="detail-list">
              <div className="detail-row"><span>Transaction ID</span><strong>{transaction.transaction_id}</strong></div>
              <div className="detail-row"><span>Date</span><strong>{formatDate(transaction.date)}</strong></div>
              <div className="detail-row"><span>Counterparty</span><strong>{transaction.counterparty || "—"}</strong></div>
              <div className="detail-row"><span>Amount</span><strong>{formatAmount(transaction)}</strong></div>
            </div>
          </div>
          <div>
            <h3>Matched supporting record</h3>
            <div className="detail-list">
              <div className="detail-row"><span>Invoice</span><strong>{transaction.matched_invoice || "No match"}</strong></div>
              <div className="detail-row"><span>Match score</span><strong>{transaction.match_score ?? "—"}</strong></div>
              <div className="detail-row"><span>Reason</span><strong>{transaction.reason || "—"}</strong></div>
            </div>
          </div>
        </div>
        <div className="original-fields-stack">
          <OriginalFields title="Original Bank Record" fields={transaction.bank_fields} />
          <OriginalFields title="Original ERP / Miscellaneous Record" fields={transaction.erp_fields} />
        </div>
      </StoryCard>

      <StoryCard step="02" kicker="DETERMINISTIC DECISION" title="Rules-based match">
        <div className="detail-list">
          <div className="detail-row"><span>Deterministic status</span><strong>{transaction.deterministic_status || "—"}</strong></div>
          <div className="detail-row"><span>Selected invoice</span><strong>{transaction.matched_invoice || "—"}</strong></div>
          <div className="detail-row"><span>Match score</span><strong>{transaction.match_score ?? "—"}</strong></div>
          <div className="detail-row"><span>Engine reason</span><strong>{transaction.reason || "—"}</strong></div>
        </div>
      </StoryCard>

      <StoryCard step="03" kicker="AI RECOMMENDATION" title="AI reasoning">
        {transaction.ai_decision ? (
          <div className="detail-list">
            <div className="detail-row"><span>AI decision</span><strong>{transaction.ai_decision}</strong></div>
            <div className="detail-row"><span>Candidate invoice</span><strong>{transaction.ai_invoice || "—"}</strong></div>
            <div className="detail-row"><span>Confidence</span><strong>{formatConfidence(transaction.ai_confidence)}</strong></div>
            <div className="detail-row"><span>Risk</span><strong>{transaction.ai_risk || "—"}</strong></div>
            <div className="detail-row"><span>Reason</span><strong>{transaction.ai_reason || "—"}</strong></div>
          </div>
        ) : (
          <p className="muted-note">AI reasoning was not used for this transaction.</p>
        )}
      </StoryCard>

      <StoryCard step="04" kicker="VERIFICATION GUARD" title="Independent checks">
        <div className="detail-list">
          <div className="detail-row">
            <span>Guard decision</span>
            <span className={`status-badge status-${finalStatus.toLowerCase()}`}>{transaction.verification_decision || "—"}</span>
          </div>
          <div className="detail-row"><span>Verification reason</span><strong>{transaction.verification_reason || "—"}</strong></div>
        </div>
        {Object.keys(checks).length > 0 && (
          <div className="check-list" style={{ marginTop: 16 }}>
            {Object.entries(checks).map(([key, value]) => (
              <span key={key} className={value === true ? "check-pass" : value === false ? "check-fail" : "check-neutral"}>
                {value === true ? "✓" : value === false ? "×" : "•"} {key.replaceAll("_", " ")}: {String(value)}
              </span>
            ))}
          </div>
        )}
      </StoryCard>

      <StoryCard step="05" kicker="HUMAN DECISION" title="Reviewer action">
        {needsReview ? (
          <div className="review-panel nested-review">
            <p>Automated reconciliation could not safely close this item.</p>
            <label className="review-note-label">Reviewer note</label>
            <textarea
              className="review-note"
              placeholder="Required when rejecting or keeping as an exception"
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
            />
            <div className="review-actions">
              <button className="review-button approve" onClick={() => handleReview("APPROVE")} disabled={reviewing}>Approve Match</button>
              <button className="review-button reject" onClick={() => handleReview("REJECT")} disabled={reviewing}>Reject Match</button>
              <button className="review-button unresolved" onClick={() => handleReview("UNRESOLVED")} disabled={reviewing}>Keep as Exception</button>
            </div>
            {reviewMessage && <div className="review-message">{reviewMessage}</div>}
            <p className="muted-note">Selecting a different candidate is not available on the current review API.</p>
          </div>
        ) : transaction.review_status === "COMPLETED" ? (
          <div className="detail-list">
            <div className="detail-row"><span>Reviewer decision</span><strong>{transaction.review_decision || "—"}</strong></div>
            <div className="detail-row"><span>Note</span><strong>{transaction.reviewer_note || "No note provided"}</strong></div>
            <div className="detail-row"><span>Reviewed at</span><strong>{transaction.reviewed_at || "—"}</strong></div>
          </div>
        ) : (
          <p className="muted-note">No human review was required for this transaction.</p>
        )}
      </StoryCard>

      <StoryCard step="06" kicker="FINAL STATUS" title={`Final status: ${finalStatus}`}>
        <p className="muted-note">This is the current operational state stored by the backend.</p>
      </StoryCard>
    </div>
  );
}
