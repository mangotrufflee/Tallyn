import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import WorkflowProgress from "../components/WorkflowProgress";
import {
  buildSupportingUpload,
  detectSourceType,
  fileExtension,
  isAllowedBankFile,
  isAllowedSupportingFile,
} from "../utils/workflow";
import {
  getMetrics,
  getSummary,
  getTransactions,
  reconcileUploadedBatch,
  validateReconciliationUpload,
} from "../services/api";

function fileMeta(file) {
  if (!file) return null;
  return {
    name: file.name,
    type: fileExtension(file).replace(".", "").toUpperCase() || "FILE",
    sourceType: detectSourceType(file),
    size: `${(file.size / 1024).toFixed(1)} KB`,
  };
}

function ValidationBlock({ info, fallback }) {
  if (!info && !fallback) return null;
  const valid = info?.valid;
  const records = info?.records;
  const errors = info?.errors || (fallback ? [fallback] : []);
  const warnings = info?.warnings || [];

  return (
    <div className={`upload-validation ${valid ? "is-valid" : valid === false ? "is-invalid" : ""}`}>
      <strong>
        {valid ? "Valid" : valid === false ? "Needs attention" : "Not validated yet"}
      </strong>
      {records !== undefined && <span>{records} records</span>}
      {info?.filename && <span>{info.filename}</span>}
      {errors.map((error) => <span key={error}>{error}</span>)}
      {warnings.map((warning) => <span key={warning}>{warning}</span>)}
    </div>
  );
}

function ProcessingPanel({ phase }) {
  const items = [
    { id: "prepare", label: "Preparing documents" },
    { id: "validate", label: "Validating data" },
    { id: "reconcile", label: "Running reconciliation pipeline" },
  ];
  const order = { prepare: 0, validate: 1, reconcile: 2, done: 3 };
  const current = order[phase] ?? 0;

  return (
    <div className="dashboard-card processing-panel">
      <h2>Reconciliation in progress</h2>
      <p>The existing matching, AI, and verification pipeline is running. This can take a few minutes.</p>
      <ul className="processing-list">
        {items.map((item, index) => {
          const done = index < current;
          const active = index === current && phase !== "done";
          return (
            <li key={item.id} className={done ? "is-done" : active ? "is-active" : ""}>
              <span>{done ? "✓" : active ? "…" : "○"}</span>
              {item.label}{active ? "..." : done ? "" : ""}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function NewReconciliation() {
  const navigate = useNavigate();
  const [bankFile, setBankFile] = useState(null);
  const [supportingFiles, setSupportingFiles] = useState([]);
  const [validation, setValidation] = useState(null);
  const [localError, setLocalError] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [results, setResults] = useState(null);

  const bankInfo = fileMeta(bankFile);
  const pdfBlocked = bankFile && fileExtension(bankFile) === ".pdf";

  const workflowStep = results ? 4 : phase === "reconcile" ? 3 : validation?.valid ? 2 : 1;
  const hint = results
    ? "Reconciliation finished. Review exceptions that still need a human decision."
    : busy
      ? "Stay on this page until the pipeline completes."
      : "Upload a bank statement, add supporting documents, then review and run.";

  const supportingSummary = useMemo(() => {
    const records = validation?.erp?.records;
    return {
      files: supportingFiles.length,
      records,
      valid: validation?.erp?.valid,
    };
  }, [supportingFiles.length, validation]);

  function resetValidation() {
    setValidation(null);
    setResults(null);
    setError("");
    setLocalError("");
  }

  function onBankChange(event) {
    const file = event.target.files?.[0] || null;
    setBankFile(file);
    resetValidation();
    if (file && !isAllowedBankFile(file)) {
      setLocalError("Bank statement must be CSV, XLSX, XLS, or PDF.");
    }
  }

  function onAddSupporting(event) {
    const incoming = Array.from(event.target.files || []);
    event.target.value = "";
    const accepted = [];
    incoming.forEach((file) => {
      if (!isAllowedSupportingFile(file)) {
        setLocalError("Supporting documents must be CSV, XLSX, or XLS.");
        return;
      }
      accepted.push(file);
    });
    if (!accepted.length) return;
    setSupportingFiles((current) => {
      const names = new Set(current.map((file) => file.name));
      return [...current, ...accepted.filter((file) => !names.has(file.name))];
    });
    resetValidation();
  }

  function removeSupporting(name) {
    setSupportingFiles((current) => current.filter((file) => file.name !== name));
    resetValidation();
  }

  async function buildForm() {
    if (!bankFile || supportingFiles.length === 0) {
      throw new Error("Upload a bank statement and at least one supporting document.");
    }
    if (pdfBlocked) {
      throw new Error(
        "PDF bank statements are shown in this workflow, but the current upload API accepts CSV, XLSX, and XLS only."
      );
    }
    const erpFile = await buildSupportingUpload(supportingFiles);
    const form = new FormData();
    form.append("bank_file", bankFile);
    form.append("erp_file", erpFile);
    return form;
  }

  async function validateFiles() {
    setError("");
    setLocalError("");
    setBusy(true);
    setPhase("prepare");
    try {
      const form = await buildForm();
      setPhase("validate");
      const result = await validateReconciliationUpload(form);
      setValidation(result);
      if (!result.valid) setError("Fix the validation issues before running reconciliation.");
    } catch (requestError) {
      setError(requestError.message || "Unable to validate uploaded files.");
    } finally {
      setBusy(false);
      setPhase("idle");
    }
  }

  async function runMatching() {
    setError("");
    setLocalError("");
    setBusy(true);
    try {
      setPhase("prepare");
      const form = await buildForm();
      setPhase("validate");
      const validationResult = await validateReconciliationUpload(form);
      setValidation(validationResult);
      if (!validationResult.valid) {
        setError("Fix the validation issues before running reconciliation.");
        return;
      }

      setPhase("reconcile");
      const matchForm = await buildForm();
      await reconcileUploadedBatch(matchForm);

      const [summary, metrics, transactions] = await Promise.all([
        getSummary(),
        getMetrics(),
        getTransactions(),
      ]);
      const list = Array.isArray(transactions) ? transactions : transactions.transactions || [];
      setResults({ summary, metrics, transactions: list });
    } catch (requestError) {
      setError(requestError.message || "Unable to run reconciliation.");
    } finally {
      setBusy(false);
      setPhase("idle");
    }
  }

  if (results) {
    const summary = results.summary;
    const metrics = results.metrics;
    const list = results.transactions;
    const deterministicMatches = list.filter(
      (row) => row.verification_decision === "MATCHED" && !row.ai_decision
    ).length;
    const aiAssisted = list.filter((row) => row.ai_decision).length;
    const humanReview = summary.review + summary.exceptions;
    const needsAction = humanReview > 0;

    return (
      <div className="page-container new-reconciliation-page">
        <div className="page-header">
          <div>
            <span className="dashboard-eyebrow">RECONCILIATION RESULTS</span>
            <h1>Batch complete</h1>
            <p>Operational outcomes from the current uploaded batch. Quality scores from Track 04 stay on the dashboard.</p>
          </div>
          <span className="batch-badge">Current batch</span>
        </div>

        <WorkflowProgress currentStep={needsAction ? 4 : 5} hint={needsAction ? "Human action is still required." : "No open exceptions remain."} />

        <div className="kpi-grid">
          <div className="kpi-card"><span className="kpi-title">Total Transactions</span><div className="kpi-value">{summary.total_transactions}</div></div>
          <div className="kpi-card"><span className="kpi-title">Matched</span><div className="kpi-value">{summary.matched}</div></div>
          <div className="kpi-card"><span className="kpi-title">Needs Review</span><div className="kpi-value">{summary.review}</div></div>
          <div className="kpi-card"><span className="kpi-title">Exceptions</span><div className="kpi-value">{summary.exceptions}</div></div>
        </div>

        <div className="performance-grid results-breakdown">
          <div className="performance-item"><span>Deterministic Matches</span><strong>{deterministicMatches}</strong><small>Matched without AI</small></div>
          <div className="performance-item"><span>AI-Assisted Cases</span><strong>{aiAssisted}</strong><small>Sent to the AI reasoner</small></div>
          <div className="performance-item"><span>AI Recommendations</span><strong>{metrics.ai_recommendations ?? 0}</strong><small>AI MATCH recommendations</small></div>
          <div className="performance-item"><span>Guard Approved</span><strong>{metrics.guard_approved ?? 0}</strong><small>AI matches verified</small></div>
          <div className="performance-item"><span>Guard Rejected</span><strong>{metrics.ai_matches_blocked ?? 0}</strong><small>AI matches blocked</small></div>
          <div className="performance-item"><span>Human Review</span><strong>{humanReview}</strong><small>Needs a human decision</small></div>
        </div>

        {needsAction && (
          <div className="dashboard-card action-needed-card">
            <div>
              <h2>{humanReview} transactions require human action</h2>
              <p>Open the exceptions queue to approve, reject, or keep items as exceptions.</p>
            </div>
            <button className="primary-button" onClick={() => navigate("/exceptions")}>
              Review Exceptions
            </button>
          </div>
        )}

        <div className="upload-button-row">
          <Link className="secondary-button button-link" to="/">Dashboard</Link>
          <Link className="secondary-button button-link" to="/verification">Verification</Link>
          <button className="secondary-button" onClick={() => { setResults(null); setValidation(null); }}>
            Start another batch
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container new-reconciliation-page">
      <div className="page-header">
        <div>
          <span className="dashboard-eyebrow">RECONCILIATION WORKFLOW</span>
          <h1>New Reconciliation</h1>
          <p>Upload a bank statement, attach supporting documents, validate, then run the existing pipeline.</p>
        </div>
        <span className="batch-badge">New batch</span>
      </div>

      <WorkflowProgress currentStep={workflowStep} hint={hint} />

      {busy && <ProcessingPanel phase={phase} />}

      <section className="upload-card workflow-step-card">
        <div className="upload-card-heading">
          <span className="upload-kicker">STEP 1 — BANK STATEMENT</span>
          <h2>Bank Statement</h2>
          <p>CSV, XLSX, XLS, or PDF. The current API reads CSV/Excel tables.</p>
        </div>
        <label className="upload-dropzone">
          <input type="file" accept=".csv,.xlsx,.xls,.pdf" onChange={onBankChange} disabled={busy} />
          <strong>{bankInfo ? bankInfo.name : "Choose bank statement"}</strong>
          <span>{bankInfo ? `${bankInfo.type} · ${bankInfo.size}` : "Select a file to continue"}</span>
        </label>
        {bankInfo && (
          <div className="file-chip-list">
            <div className="file-chip">
              <div>
                <strong>{bankInfo.name}</strong>
                <span>{bankInfo.type} · {bankInfo.sourceType}</span>
              </div>
              <span>{validation?.bank?.records != null ? `${validation.bank.records} records` : "Pending validation"}</span>
            </div>
          </div>
        )}
        <ValidationBlock
          info={validation?.bank}
          fallback={pdfBlocked ? "PDF is listed for this step, but the upload API currently accepts CSV, XLSX, and XLS only." : ""}
        />
      </section>

      <section className="upload-card workflow-step-card">
        <div className="upload-card-heading">
          <span className="upload-kicker">STEP 2 — SUPPORTING DOCUMENTS</span>
          <h2>Supporting Documents</h2>
          <p>Add multiple ERP, settlement, or invoice files. CSV files are combined automatically for the existing single-file API.</p>
        </div>

        <div className="file-chip-list">
          {supportingFiles.map((file) => {
            const meta = fileMeta(file);
            return (
              <div className="file-chip" key={file.name}>
                <div>
                  <strong>{meta.name}</strong>
                  <span>{meta.sourceType} · {meta.type}</span>
                </div>
                <div className="file-chip-meta">
                  <span>{validation?.erp && supportingFiles.length === 1 && validation.erp.records != null ? `${validation.erp.records} records` : meta.size}</span>
                  <span className={validation?.erp?.valid ? "chip-ok" : ""}>{validation?.erp ? (validation.erp.valid ? "✓" : "Needs review") : "Queued"}</span>
                  <button type="button" className="chip-remove" onClick={() => removeSupporting(file.name)} disabled={busy}>Remove</button>
                </div>
              </div>
            );
          })}
        </div>

        <label className="add-document-button">
          <input type="file" accept=".csv,.xlsx,.xls" multiple onChange={onAddSupporting} disabled={busy} />
          + Add Document
        </label>
        <ValidationBlock info={validation?.erp} />
      </section>

      <section className="dashboard-card workflow-step-card">
        <div className="upload-card-heading">
          <span className="upload-kicker">STEP 3 — REVIEW</span>
          <h2>Review & Validate Files</h2>
        </div>
        <div className="review-summary-grid">
          <div>
            <span>Bank Statement</span>
            <strong>1 file</strong>
            <small>
              {bankFile ? `${validation?.bank?.records ?? "—"} records · ${validation?.bank?.valid ? "Valid" : validation ? "Invalid" : "Not validated"}` : "No file"}
            </small>
          </div>
          <div>
            <span>Supporting Documents</span>
            <strong>{supportingSummary.files} file{supportingSummary.files === 1 ? "" : "s"}</strong>
            <small>
              {supportingFiles.length
                ? `${validation?.erp?.records ?? "—"} records · ${validation?.erp?.valid ? "Valid" : validation ? "Invalid" : "Not validated"}`
                : "No files"}
            </small>
          </div>
        </div>
        <div className="upload-button-row">
          <button className="secondary-button" onClick={validateFiles} disabled={busy || !bankFile || !supportingFiles.length}>
            {busy && phase !== "reconcile" ? "Checking..." : "Validate Files"}
          </button>
          <button className="primary-button" onClick={runMatching} disabled={busy || !bankFile || !supportingFiles.length}>
            {busy && phase === "reconcile" ? "Running..." : "Run Reconciliation"}
          </button>
        </div>
      </section>

      {(error || localError) && (
        <div className="page-error upload-error">{error || localError}</div>
      )}
    </div>
  );
}
