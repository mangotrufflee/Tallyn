import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";

import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";

import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Exceptions from "./pages/Exceptions";
import TransactionDetails from "./pages/TransactionDetails";
import AIInsights from "./pages/AIInsights";
import Verification from "./pages/Verification";
import NewReconciliation from "./pages/NewReconciliation";
import PastRecords from "./pages/PastRecords";

import "./App.css";

function AppShell() {
  const location = useLocation();
  const hideSidebar = ["/", "/new-reconciliation"].includes(location.pathname);

  return (
    <div className="app-shell">
      {!hideSidebar && <Sidebar />}

      <div className="app-body">
        <Topbar compact={hideSidebar} />

        <main className="main-content">
          <Routes>
            <Route path="/" element={<NewReconciliation />} />
            <Route path="/new-reconciliation" element={<NewReconciliation />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/past-records" element={<PastRecords />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/exceptions" element={<Exceptions />} />
            <Route path="/ai-cases" element={<Exceptions />} />
            <Route path="/transactions/:transactionId" element={<TransactionDetails />} />
            <Route path="/ai-insights" element={<AIInsights />} />
            <Route path="/verification" element={<Verification />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}

export default App;