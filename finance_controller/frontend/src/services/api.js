const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8001";


// ============================================================
// SUMMARY
// ============================================================

export async function getSummary() {

  const response = await fetch(
    `${API_BASE_URL}/summary`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to fetch summary"
    );
  }

  return response.json();
}


// ============================================================
// METRICS
// ============================================================

export async function getMetrics() {

  const response = await fetch(
    `${API_BASE_URL}/metrics`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to fetch metrics"
    );
  }

  return response.json();
}


// ============================================================
// TRANSACTIONS
// ============================================================

export async function getTransactions() {

  const response = await fetch(
    `${API_BASE_URL}/transactions`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to fetch transactions"
    );
  }

  return response.json();
}


// ============================================================
// SINGLE TRANSACTION
// ============================================================

export async function getTransaction(
  transactionId
) {

  const response = await fetch(
    `${API_BASE_URL}/transactions/${transactionId}`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to fetch transaction"
    );
  }

  return response.json();
}


// ============================================================
// EXCEPTIONS
// ============================================================

export async function getExceptions() {

  const response = await fetch(
    `${API_BASE_URL}/exceptions`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to fetch exceptions"
    );
  }

  return response.json();
}


// ============================================================
// HUMAN REVIEW
// ============================================================

export async function reviewTransaction(

  transactionId,

  decision,

  note = ""

) {

  const response = await fetch(

    `${API_BASE_URL}/transactions/${transactionId}/review`,

    {

      method: "POST",

      headers: {

        "Content-Type":
          "application/json",
      },

      body: JSON.stringify({

        decision,

        note,
      }),
    }
  );


  if (!response.ok) {

    const error =
      await response
        .json()
        .catch(() => ({}));


    throw new Error(

      error.detail ||
      "Failed to submit review"
    );
  }


  return response.json();
}

// ============================================================
// AI INSIGHTS
// ============================================================

export async function getAIInsights() {

  const response = await fetch(
    `${API_BASE_URL}/ai-insights`
  );

  if (!response.ok) {

    throw new Error(
      "Failed to fetch AI insights"
    );
  }

  return response.json();
}

export async function getVerification() {
  const response = await fetch(`${API_BASE_URL}/verification`);

  if (!response.ok) {
    throw new Error("Failed to fetch verification data");
  }

  return response.json();
}

export async function reconcileTransactions() {
  const response = await fetch(`${API_BASE_URL}/reconcile`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error("Failed to reconcile transactions");
  }

  return response.json();
}