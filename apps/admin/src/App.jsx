import { Navigate, Route, Routes } from "react-router-dom";
import Layout, { RequireAuth } from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Stub from "./pages/Stub";
import Users from "./pages/Users";

// Sections that only exist as sidebar entries for now — each renders the Stub page.
const STUB_ROUTES = [
  { path: "groups", titleKey: "nav.groups" },
  { path: "downloads", titleKey: "nav.downloads" },
  { path: "plans", titleKey: "nav.plans" },
  { path: "payments", titleKey: "nav.payments" },
  { path: "platforms", titleKey: "nav.platforms" },
  { path: "providers", titleKey: "nav.providers" },
  { path: "ads", titleKey: "nav.ads" },
  { path: "forced-join", titleKey: "nav.forcedJoin" },
  { path: "languages", titleKey: "nav.languages" },
  { path: "bot-texts", titleKey: "nav.botTexts" },
  { path: "broadcast", titleKey: "nav.broadcast" },
  { path: "admins", titleKey: "nav.admins" },
  { path: "settings", titleKey: "nav.settings" },
  { path: "backup", titleKey: "nav.backup" },
  { path: "update", titleKey: "nav.update" },
  { path: "health", titleKey: "nav.health" },
];

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="users" element={<Users />} />
        {STUB_ROUTES.map(({ path, titleKey }) => (
          <Route key={path} path={path} element={<Stub titleKey={titleKey} />} />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
