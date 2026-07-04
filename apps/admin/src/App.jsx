import { Navigate, Route, Routes } from "react-router-dom";
import Layout, { RequireAuth } from "./components/Layout";
import Ads from "./pages/Ads";
import BotTexts from "./pages/BotTexts";
import Dashboard from "./pages/Dashboard";
import Downloads from "./pages/Downloads";
import ForcedJoin from "./pages/ForcedJoin";
import Groups from "./pages/Groups";
import Login from "./pages/Login";
import Payments from "./pages/Payments";
import Plans from "./pages/Plans";
import Platforms from "./pages/Platforms";
import Providers from "./pages/Providers";
import Settings from "./pages/Settings";
import Stub from "./pages/Stub";
import Users from "./pages/Users";

// Sections that only exist as sidebar entries for now — each renders the Stub page.
const STUB_ROUTES = [
  { path: "languages", titleKey: "nav.languages" },
  { path: "broadcast", titleKey: "nav.broadcast" },
  { path: "admins", titleKey: "nav.admins" },
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
        <Route path="groups" element={<Groups />} />
        <Route path="downloads" element={<Downloads />} />
        <Route path="plans" element={<Plans />} />
        <Route path="payments" element={<Payments />} />
        <Route path="platforms" element={<Platforms />} />
        <Route path="providers" element={<Providers />} />
        <Route path="settings" element={<Settings />} />
        <Route path="ads" element={<Ads />} />
        <Route path="forced-join" element={<ForcedJoin />} />
        <Route path="bot-texts" element={<BotTexts />} />
        {STUB_ROUTES.map(({ path, titleKey }) => (
          <Route key={path} path={path} element={<Stub titleKey={titleKey} />} />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
