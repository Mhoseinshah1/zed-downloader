import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { useLang } from "../i18n";
import { getStoredAdmin, isAuthenticated, logout, me } from "../services/auth";

// Protected-route wrapper: bounce to /login when there is no access token.
export function RequireAuth({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

// Sidebar entries. Dashboard and Users are live; the rest route to Stub pages.
const NAV_ITEMS = [
  { to: "/", key: "nav.dashboard", end: true },
  { to: "/users", key: "nav.users" },
  { to: "/groups", key: "nav.groups" },
  { to: "/downloads", key: "nav.downloads" },
  { to: "/plans", key: "nav.plans" },
  { to: "/payments", key: "nav.payments" },
  { to: "/platforms", key: "nav.platforms" },
  { to: "/providers", key: "nav.providers" },
  { to: "/ads", key: "nav.ads" },
  { to: "/forced-join", key: "nav.forcedJoin" },
  { to: "/languages", key: "nav.languages" },
  { to: "/bot-texts", key: "nav.botTexts" },
  { to: "/broadcast", key: "nav.broadcast" },
  { to: "/admins", key: "nav.admins" },
  { to: "/settings", key: "nav.settings" },
  { to: "/backup", key: "nav.backup" },
  { to: "/update", key: "nav.update" },
  { to: "/health", key: "nav.health" },
];

export default function Layout() {
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const [admin, setAdmin] = useState(getStoredAdmin());

  // Fill in the topbar identity if it was not cached at login time.
  useEffect(() => {
    if (!admin) {
      me()
        .then(setAdmin)
        .catch(() => {
          // 401 handling (refresh / redirect) is done by the api interceptor.
        });
    }
  }, [admin]);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  function toggleLang() {
    setLang(lang === "fa" ? "en" : "fa");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true">
            Z
          </span>
          <div>
            <div className="sidebar__title">{t("app.title")}</div>
            <div className="sidebar__subtitle">{t("app.subtitle")}</div>
          </div>
        </div>
        <nav className="sidebar__nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                "sidebar__link" + (isActive ? " sidebar__link--active" : "")
              }
            >
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="topbar__side">
            <button
              type="button"
              className="btn btn--ghost topbar__lang"
              onClick={toggleLang}
              title={lang === "fa" ? "Switch to English" : "تغییر به فارسی"}
            >
              {lang === "fa" ? "EN" : "فا"}
            </button>
          </div>
          <div className="topbar__side topbar__side--end">
            {admin && <span className="topbar__email">{admin.email}</span>}
            <button type="button" className="btn btn--ghost" onClick={handleLogout}>
              {t("common.logout")}
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
