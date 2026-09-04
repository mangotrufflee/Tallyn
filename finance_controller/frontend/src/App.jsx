import { BrowserRouter, Routes, Route } from "react-router-dom";

import Sidebar from "./components/Sidebar";

import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Exceptions from "./pages/Exceptions";
import TransactionDetails from "./pages/TransactionDetails";

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

          </Routes>

        </main>

      </div>

    </BrowserRouter>
  );
}

export default App;