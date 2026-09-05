import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getRecords } from "../services/api";

function formatDateLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function PastRecords() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const data = await getRecords();
        setRecords(Array.isArray(data) ? data : []);
      } catch (err) {
        setError(err.message || "Unable to load past records.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <div className="empty-state">
          <h3>Loading past records...</h3>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="empty-state">
          <h3>Unable to load records</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <span className="dashboard-eyebrow">PAST RECORDS</span>
          <h1>Historical uploads</h1>
          <p>Review recorded datasets and open the dashboard for each upload.</p>
        </div>
      </div>

      <div className="dashboard-card transaction-card">
        <div className="table-header">
          <div>
            <h2>Available datasets</h2>
            <p>
              Showing <strong>{records.length}</strong> dataset records
            </p>
          </div>
        </div>

        <div className="table-wrapper">
          <table className="transaction-table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Files uploaded</th>
                <th>Transactions</th>
                <th>Uploaded</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {records.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    <strong>{entry.batch_id}</strong>
                    <span className="invoice-subtext">Backend dataset record</span>
                  </td>
                  <td>Not recorded</td>
                  <td>{entry.transactions}</td>
                  <td>{formatDateLabel(entry.uploaded_at)}</td>
                  <td>{entry.processing_status}</td>
                  <td>
                    <Link to="/dashboard" className="view-link">
                      View Dashboard →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
