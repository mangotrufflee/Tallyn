import { BrowserRouter, Routes, Route } from "react-router-dom";

import Sidebar from "./components/Sidebar";

import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Exceptions from "./pages/Exceptions";
import TransactionDetails from "./pages/TransactionDetails";
import AIInsights from "./pages/AIInsights";
import Verification from "./pages/Verification";

import "./App.css";

function App() {
  return (
    <BrowserRouter>

      <div className="app">

        <Sidebar />

        <main className="main-content">

          <Routes>

            <Route
              path="/"
              element={<Dashboard />}
            />

            <Route
              path="/transactions"
              element={<Transactions />}
            />

            <Route
              path="/exceptions"
              element={<Exceptions />}
            />

            <Route
              path="/transactions/:transactionId"
              element={<TransactionDetails />}
            />

            <Route
              path="/ai-insights"
              element={<AIInsights />}
            />

            <Route path="/verification" element={<Verification />} />

          </Routes>

        </main>

      </div>

    </BrowserRouter>
  );
}

export default App;