import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  reconcileUploadedBatch,
  validateReconciliationUpload,
} from "../services/api";

function UploadCard({ title, file, onChange, info }) {
  return (
    <section className="upload-card">
      <div className="upload-card-heading">
        <span className="upload-kicker">INPUT DATA</span>
        <h2>{title}</h2>
        <p>CSV or Excel files with the original records.</p>
      </div>
      <label className="upload-dropzone">
        <input type="file" accept=".csv,.xlsx,.xls" onChange={onChange} />
        <strong>{file ? file.name : "Choose CSV / Excel"}</strong>
        <span>{file ? `${(file.size / 1024).toFixed(1)} KB` : "Select a file to validate"}</span>
      </label>
      {info && (
        <div className={`upload-validation ${info.valid ? "is-valid" : "is-invalid"}`}>
          <strong>{info.valid ? "Ready to use" : "Needs attention"}</strong>
          {info.records !== undefined && <span>{info.records} records detected</span>}
          {info.columns && <span>{info.columns.join(", ")}</span>}
          {info.errors?.map((error) => <span key={error}>{error}</span>)}
        </div>
      )}
    </section>
  );
}

export default function NewReconciliation() {
  const navigate = useNavigate();
  const [bankFile, setBankFile] = useState(null);
  const [erpFile, setErpFile] = useState(null);
  const [validation, setValidation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function validateFiles() {
    if (!bankFile || !erpFile) {
      setError("Upload both Bank Records and Miscellaneous / ERP Records first.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("bank_file", bankFile);
      form.append("erp_file", erpFile);
      const result = await validateReconciliationUpload(form);
      setValidation(result);
      if (!result.valid) setError("Fix the validation issues before matching.");
    } catch (requestError) {
      setError(requestError.message || "Unable to validate uploaded files.");
    } finally {
      setBusy(false);
    }
  }

  async function runMatching() {
    if (!bankFile || !erpFile) return;
    setError("");
    setBusy(true);
    try {
      const validationForm = new FormData();
      validationForm.append("bank_file", bankFile);
      validationForm.append("erp_file", erpFile);
      const validationResult = await validateReconciliationUpload(validationForm);
      setValidation(validationResult);
      if (!validationResult.valid) {
        setError("Fix the validation issues before matching.");
        return;
      }

      const matchForm = new FormData();
      matchForm.append("bank_file", bankFile);
      matchForm.append("erp_file", erpFile);
      await reconcileUploadedBatch(matchForm);
      navigate("/");
    } catch (requestError) {
      setError(requestError.message || "Unable to run reconciliation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container new-reconciliation-page">
      <div className="page-header">
        <div>
          <span className="dashboard-eyebrow">CONTROLLED BATCH INPUT</span>
          <h1>New Reconciliation</h1>
          <p>Load a bank file and its corresponding miscellaneous or ERP records.</p>
        </div>
        <span className="batch-badge">New batch</span>
      </div>

      <div className="upload-grid">
        <UploadCard
          title="Bank Records"
          file={bankFile}
          onChange={(event) => { setBankFile(event.target.files?.[0] || null); setValidation(null); }}
          info={validation?.bank}
        />
        <UploadCard
          title="Miscellaneous / ERP Records"
          file={erpFile}
          onChange={(event) => { setErpFile(event.target.files?.[0] || null); setValidation(null); }}
          info={validation?.erp}
        />
      </div>

      <div className="upload-actions dashboard-card">
        <div>
          <h2>Ready to reconcile?</h2>
          <p>Files are validated before the existing matching, AI, and verification pipeline runs.</p>
        </div>
        <div className="upload-button-row">
          <button className="secondary-button" onClick={validateFiles} disabled={busy || !bankFile || !erpFile}>
            {busy ? "Checking..." : "Validate Files"}
          </button>
          <button className="primary-button" onClick={runMatching} disabled={busy || !bankFile || !erpFile}>
            {busy ? "Matching..." : "Do the Matching"}
          </button>
        </div>
      </div>

      {error && <div className="page-error upload-error">{error}</div>}
    </div>
  );
}
