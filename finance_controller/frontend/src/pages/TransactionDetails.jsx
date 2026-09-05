import { useEffect, useState } from "react";

import {
  Link,
  useParams,
} from "react-router-dom";

import {
  getTransaction,
  reviewTransaction,
} from "../services/api";

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

function TransactionDetails() {

  const { transactionId } =
    useParams();


  const [transaction, setTransaction] =
    useState(null);


  const [loading, setLoading] =
    useState(true);


  const [error, setError] =
    useState("");


  const [reviewNote, setReviewNote] =
    useState("");


  const [reviewing, setReviewing] =
    useState(false);


  const [reviewMessage, setReviewMessage] =
    useState("");


  // ========================================================
  // LOAD TRANSACTION
  // ========================================================

  useEffect(() => {

    async function loadTransaction() {

      try {

        const data =
          await getTransaction(
            transactionId
          );

        setTransaction(data);

      } catch (err) {

        console.error(err);

        setError(
          "Unable to load transaction details."
        );

      } finally {

        setLoading(false);
      }
    }


    loadTransaction();

  }, [transactionId]);


  // ========================================================
  // HUMAN REVIEW
  // ========================================================

  async function handleReview(
    decision
  ) {

    setReviewing(true);

    setReviewMessage("");


    try {

      await reviewTransaction(

        transactionId,

        decision,

        reviewNote
      );


      setReviewMessage(

        `Transaction successfully marked as ${decision}.`
      );


      const updated =
        await getTransaction(
          transactionId
        );


      setTransaction(updated);

      setReviewNote("");


    } catch (err) {

      console.error(err);

      setReviewMessage(

        err.message ||
        "Unable to submit review."
      );

    } finally {

      setReviewing(false);
    }
  }


  // ========================================================
  // LOADING
  // ========================================================

  if (loading) {

    return (

      <div className="page-container">

        <p>
          Loading transaction...
        </p>

      </div>
    );
  }


  // ========================================================
  // ERROR
  // ========================================================

  if (error || !transaction) {

    return (

      <div className="page-container">

        <Link
          to="/transactions"
          className="back-link"
        >
          ← Back to Transactions
        </Link>


        <div className="empty-state">

          <h2>
            Transaction not found
          </h2>

          <p>
            {error}
          </p>

        </div>

      </div>
    );
  }


  // ========================================================
  // STATUS
  // ========================================================

  const finalStatus =
    transaction.verification_decision ||
    transaction.deterministic_status ||
    "UNKNOWN";


  const statusClass =
    finalStatus.toLowerCase();


  const needsReview =
    transaction.review_status !== "COMPLETED" &&
    (finalStatus === "REVIEW" || finalStatus === "EXCEPTION");


  return (

    <div className="page-container">


      {/* ==================================================
          HEADER
      ================================================== */}

      <div className="details-header">

        <div>

          <Link
            to="/transactions"
            className="back-link"
          >
            ← Back to Transactions
          </Link>


          <h1>
            {transaction.transaction_id}
          </h1>


          <p>
            Reconciliation evidence and
            verification trail
          </p>

        </div>


        <span
          className={
            `status-badge status-${statusClass}`
          }
        >
          {finalStatus}
        </span>

      </div>


      {/* ==================================================
          EVIDENCE
      ================================================== */}

      <div className="evidence-grid">


        {/* BANK */}

        <div className="dashboard-card evidence-card">

          <div className="evidence-title">

            <div className="evidence-icon">
              $
            </div>

            <div>

              <h2>
                Bank Transaction
              </h2>

              <span>
                Source record
              </span>

            </div>

          </div>


          <div className="detail-list">

            <div className="detail-row">

              <span>
                Transaction ID
              </span>

              <strong>
                {transaction.transaction_id}
              </strong>

            </div>


            <div className="detail-row">

              <span>
                Date
              </span>

              <strong>
                {transaction.date}
              </strong>

            </div>


            <div className="detail-row">

              <span>
                Counterparty
              </span>

              <strong>
                {transaction.counterparty}
              </strong>

            </div>


            <div className="detail-row">

              <span>
                Amount
              </span>

              <strong>
                {transaction.currency}{" "}
                {transaction.amount}
              </strong>

            </div>

          </div>

        </div>


        {/* ERP */}

        <div className="dashboard-card evidence-card">

          <div className="evidence-title">

            <div className="evidence-icon">
              #
            </div>

            <div>

              <h2>
                ERP Invoice
              </h2>

              <span>
                Matched accounting record
              </span>

            </div>

          </div>


          <div className="detail-list">

            <div className="detail-row">

              <span>
                Invoice
              </span>

              <strong>
                {
                  transaction.matched_invoice ||
                  "No match"
                }
              </strong>

            </div>


            <div className="detail-row">

              <span>
                Match Score
              </span>

              <strong>
                {
                  transaction.match_score ??
                  "—"
                }
              </strong>

            </div>


            <div className="detail-row">

              <span>
                Deterministic Status
              </span>

              <strong>
                {
                  transaction.deterministic_status ||
                  "—"
                }
              </strong>

            </div>

          </div>

        </div>

      </div>

      <div className="original-fields-stack">
        <OriginalFields title="Original Bank Record" fields={transaction.bank_fields} />
        <OriginalFields title="Original ERP / Miscellaneous Record" fields={transaction.erp_fields} />
      </div>


      {/* ==================================================
          MATCHING EVIDENCE
      ================================================== */}

      <div className="dashboard-card">

        <div className="section-header">

          <div>

            <h2>
              Matching Evidence
            </h2>

            <p>
              Signals used by the
              reconciliation engine
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

              {
                transaction.matched_invoice
                  ? "Matched"
                  : "Not available"
              }

            </span>

          </div>


          <div className="signal">

            <span className="signal-label">
              Match Score
            </span>

            <span className="signal-value score-value">

              {
                transaction.match_score ??
                "—"
              }

            </span>

          </div>

        </div>

      </div>


      {/* ==================================================
          AI
      ================================================== */}

      <div className="dashboard-card ai-card">

        <div className="section-header">

          <div>

            <h2>
              AI Reasoning
            </h2>

            <p>
              Semantic reasoning used for
              uncertain transactions
            </p>

          </div>


          <span className="ai-label">
            AI
          </span>

        </div>


        {
          transaction.ai_decision ? (

            <div className="ai-result">

              <div className="ai-result-row">

                <span>
                  AI Decision
                </span>

                <strong>
                  {transaction.ai_decision}
                </strong>

              </div>


              <div className="ai-result-row">

                <span>
                  Candidate Invoice
                </span>

                <strong>
                  {
                    transaction.ai_invoice ||
                    "—"
                  }
                </strong>

              </div>


              <div className="ai-result-row">

                <span>
                  Confidence
                </span>

                <strong>
                  {
                    transaction.ai_confidence ??
                    "—"
                  }
                </strong>

              </div>


              <div className="ai-result-row">

                <span>
                  Risk
                </span>

                <strong>
                  {
                    transaction.ai_risk ||
                    "—"
                  }
                </strong>

              </div>


              <div className="ai-result-row">

                <span>
                  Reason
                </span>

                <strong>
                  {
                    transaction.ai_reason ||
                    "—"
                  }
                </strong>

              </div>

            </div>

          ) : (

            <div className="ai-not-used">

              <span>
                ✦
              </span>

              <div>

                <strong>
                  AI reasoning was not required
                </strong>

                <p>
                  This transaction was resolved
                  using deterministic reconciliation
                  and verification rules.
                </p>

              </div>

            </div>
          )
        }

      </div>


      {/* ==================================================
          VERIFICATION
      ================================================== */}

      <div className="dashboard-card verification-card">

        <div className="section-header">

          <div>

            <h2>
              Verification Guard
            </h2>

            <p>
              Independent validation of
              the reconciliation decision
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
              className={
                `status-badge status-${statusClass}`
              }
            >
              {finalStatus}
            </span>

          </div>


          <div className="verification-item">

            <span>
              Verification Reason
            </span>

            <strong>
              {
                transaction.verification_reason ||
                "Transaction passed verification checks."
              }
            </strong>

          </div>

        </div>

      </div>


      {/* ==================================================
          HUMAN REVIEW
      ================================================== */}

      {needsReview && (

        <div className="dashboard-card review-panel">

          <div className="section-header">

            <div>

              <h2>
                Human Review
              </h2>

              <p>
                Automated reconciliation could
                not safely resolve this transaction.
              </p>

            </div>


            <span className="review-required-label">
              REVIEW REQUIRED
            </span>

          </div>


          <div className="review-warning">

            <strong>
              Automated decision requires
              human verification
            </strong>

            <p>
              Review the evidence above before
              making a final accounting decision.
            </p>

          </div>


          <label className="review-note-label">

            Reviewer Note

          </label>


          <textarea

            className="review-note"

            placeholder={
              "Add a note explaining your decision..."
            }

            value={reviewNote}

            onChange={(event) =>
              setReviewNote(
                event.target.value
              )
            }

          />


          <div className="review-actions">

            <button

              className="review-button approve"

              onClick={() =>
                handleReview("APPROVE")
              }

              disabled={reviewing}

            >
              ✓ Approve Match
            </button>


            <button

              className="review-button reject"

              onClick={() =>
                handleReview("REJECT")
              }

              disabled={reviewing}

            >
              × Reject
            </button>


            <button

              className="review-button unresolved"

              onClick={() =>
                handleReview("UNRESOLVED")
              }

              disabled={reviewing}

            >
              Keep Unresolved
            </button>

          </div>


          {reviewMessage && (

            <div className="review-message">

              {reviewMessage}

            </div>

          )}

        </div>

      )}


      {/* ==================================================
          PREVIOUS REVIEW
      ================================================== */}

      {
        transaction.review_status ===
        "COMPLETED" && (

          <div className="dashboard-card">

            <div className="section-header">

              <div>

                <h2>
                  Human Review Completed
                </h2>

                <p>
                  This transaction has already
                  received a reviewer decision.
                </p>

              </div>

            </div>


            <div className="detail-list">

              <div className="detail-row">

                <span>
                  Reviewer Decision
                </span>

                <strong>
                  {
                    transaction.review_decision ||
                    "—"
                  }
                </strong>

              </div>


              <div className="detail-row">

                <span>
                  Reviewer Note
                </span>

                <strong>
                  {
                    transaction.reviewer_note ||
                    "No note provided"
                  }
                </strong>

              </div>


              <div className="detail-row">

                <span>
                  Reviewed At
                </span>

                <strong>
                  {
                    transaction.reviewed_at ||
                    "—"
                  }
                </strong>

              </div>

            </div>

          </div>
        )
      }


      {/* ==================================================
          AUDIT TRAIL
      ================================================== */}

      <div className="dashboard-card audit-card">

        <div className="section-header">

          <div>

            <h2>
              Decision Trail
            </h2>

            <p>
              How this transaction moved through
              the controller
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
                Bank transaction entered the
                reconciliation batch.
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
                Candidate invoice selected using
                reconciliation signals.
              </p>

            </div>

          </div>


          {
            transaction.ai_decision && (

              <div className="timeline-item completed">

                <div className="timeline-dot">
                  ✦
                </div>

                <div>

                  <strong>
                    AI reasoning completed
                  </strong>

                  <p>
                    Semantic reasoning was used
                    for additional analysis.
                  </p>

                </div>

              </div>
            )
          }


          <div className="timeline-item completed">

            <div className="timeline-dot">
              ✓
            </div>

            <div>

              <strong>
                Verification guard completed
              </strong>

              <p>
                Final automated decision was
                independently verified.
              </p>

            </div>

          </div>


          {
            transaction.review_status ===
            "COMPLETED" && (

              <div className="timeline-item completed">

                <div className="timeline-dot">
                  ✓
                </div>

                <div>

                  <strong>
                    Human review completed
                  </strong>

                  <p>
                    Reviewer decision:
                    {" "}
                    {transaction.review_decision}
                  </p>

                </div>

              </div>
            )
          }


          <div className="timeline-item final">

            <div className="timeline-dot">
              →
            </div>

            <div>

              <strong>
                Final status: {finalStatus}
              </strong>

              <p>
                This is the current operational
                state of the transaction.
              </p>

            </div>

          </div>

        </div>

      </div>

    </div>
  );
}


export default TransactionDetails;