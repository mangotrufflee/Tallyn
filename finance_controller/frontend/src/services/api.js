const API_BASE_URL = "http://127.0.0.1:8000";

export async function getSummary() {
  const response = await fetch(`${API_BASE_URL}/summary`);

  if (!response.ok) {
    throw new Error("Failed to fetch summary");
  }

  return response.json();
}

export async function getMetrics() {
  const response = await fetch(`${API_BASE_URL}/metrics`);

  if (!response.ok) {
    throw new Error("Failed to fetch metrics");
  }

  return response.json();
}

export async function getTransactions() {
  const response = await fetch(`${API_BASE_URL}/transactions`);

  if (!response.ok) {
    throw new Error("Failed to fetch transactions");
  }

  return response.json();
}

export async function getTransaction(transactionId) {
  const response = await fetch(
    `${API_BASE_URL}/transactions/${transactionId}`
  );

  if (!response.ok) {
    throw new Error("Failed to fetch transaction");
  }

  return response.json();
}

export async function getExceptions() {
  const response = await fetch(`${API_BASE_URL}/exceptions`);

  if (!response.ok) {
    throw new Error("Failed to fetch exceptions");
  }

  return response.json();
}