import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useLang } from "../i18n";
import { isAuthenticated, login } from "../services/auth";

export default function Login() {
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated()) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      const status = err.response ? err.response.status : null;
      // 401/403 -> bad credentials; anything else -> generic connectivity error.
      setError(status === 401 || status === 403 ? "login.invalid" : "login.error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__head">
          <span className="sidebar__logo" aria-hidden="true">
            Z
          </span>
          <div>
            <h1 className="login-card__title">{t("app.title")}</h1>
            <p className="login-card__subtitle">{t("login.title")}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field">
            <span className="field__label">{t("login.email")}</span>
            <input
              type="email"
              dir="ltr"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field__label">{t("login.password")}</span>
            <input
              type="password"
              dir="ltr"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {error && <div className="form-error">{t(error)}</div>}

          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting ? t("login.submitting") : t("login.submit")}
          </button>
        </form>

        <button
          type="button"
          className="btn btn--ghost login-card__lang"
          onClick={() => setLang(lang === "fa" ? "en" : "fa")}
        >
          {lang === "fa" ? "English" : "فارسی"}
        </button>
      </div>
    </div>
  );
}
