import { Link, Route, Routes } from "react-router-dom";

import { HomePage } from "./HomePage";
import { SettingsPage } from "./SettingsPage";

export function App() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <Link className="brand" to="/">
          LeaveNow
        </Link>
        <Link className="settings-link" to="/settings">
          Settings
        </Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
