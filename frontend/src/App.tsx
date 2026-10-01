// frontend/src/App.tsx

import { Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import Dashboard from "./pages/Dashboard";
import Inventory from "./pages/Inventory";
import Sales from "./pages/Sales";
import Forecast from "./pages/Forecast";
import Stockout from "./pages/Stockout";
import Reorder from "./pages/Reorder";
import Chatbot from "./pages/Chatbot";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/stockout" element={<Stockout />} />
          <Route path="/reorder" element={<Reorder />} />
          <Route path="/chat" element={<Chatbot />} />
        </Routes>
      </main>
    </div>
  );
}
