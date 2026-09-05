const CSV_TYPES = [".csv"];
const TABULAR_TYPES = [".csv", ".xlsx", ".xls"];
const BANK_TYPES = [".csv", ".xlsx", ".xls", ".pdf"];

export function fileExtension(file) {
  const name = file?.name || "";
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function detectSourceType(file) {
  const name = (file?.name || "").toLowerCase();
  if (name.includes("razorpay") || name.includes("settlement")) return "Settlement";
  if (name.includes("invoice")) return "Invoices";
  if (name.includes("erp") || name.includes("ledger")) return "ERP export";
  if (name.includes("bank") || name.includes("statement")) return "Bank statement";
  const ext = fileExtension(file);
  if (ext === ".pdf") return "PDF statement";
  if (ext === ".csv") return "CSV";
  if (ext === ".xlsx" || ext === ".xls") return "Spreadsheet";
  return "Supporting document";
}

export function isAllowedBankFile(file) {
  return BANK_TYPES.includes(fileExtension(file));
}

export function isAllowedSupportingFile(file) {
  return TABULAR_TYPES.includes(fileExtension(file));
}

export function isCsvFile(file) {
  return CSV_TYPES.includes(fileExtension(file));
}

export async function mergeCsvFiles(files) {
  const texts = await Promise.all(files.map((file) => file.text()));
  const parsed = texts.map((text) => text.replace(/^\uFEFF/, "").trim());
  const nonEmpty = parsed.filter(Boolean);
  if (nonEmpty.length === 0) {
    throw new Error("Supporting documents contain no CSV content.");
  }

  const [first, ...rest] = nonEmpty;
  const header = first.split(/\r?\n/, 1)[0];
  const body = [first];

  rest.forEach((text) => {
    const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
    if (lines.length === 0) return;
    const nextHeader = lines[0];
    const rows = nextHeader === header ? lines.slice(1) : lines;
    if (rows.length) body.push(rows.join("\n"));
  });

  const blob = new Blob([body.join("\n")], { type: "text/csv" });
  return new File([blob], "supporting_documents.csv", { type: "text/csv" });
}

export async function buildSupportingUpload(files) {
  if (!files.length) {
    throw new Error("Upload at least one supporting document.");
  }
  if (files.length === 1) {
    return files[0];
  }
  if (files.every(isCsvFile)) {
    return mergeCsvFiles(files);
  }
  throw new Error(
    "Multiple supporting documents can be combined automatically only when they are CSV files. Combine Excel workbooks into one file, or convert them to CSV."
  );
}

export function parseChecks(raw) {
  if (!raw) return {};
  if (typeof raw === "object") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    try {
      const jsonish = String(raw)
        .replace(/\bTrue\b/g, "true")
        .replace(/\bFalse\b/g, "false")
        .replace(/\bNone\b/g, "null")
        .replace(/'/g, '"');
      return JSON.parse(jsonish);
    } catch {
      return {};
    }
  }
}

export function hasGroundTruth(metrics) {
  if (!metrics) return false;
  return (metrics.true_positive || 0) + (metrics.false_negative || 0) > 0;
}

export function formatAmount(transaction) {
  const currency = transaction?.currency === "INR" ? "₹" : transaction?.currency || "";
  const amount = Number(transaction?.amount || 0).toLocaleString("en-IN");
  return `${currency}${amount}`;
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
