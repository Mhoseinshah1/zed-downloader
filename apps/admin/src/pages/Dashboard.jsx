import { useCallback, useEffect, useState } from "react";
import HealthBadge from "../components/HealthBadge";
import StatCard from "../components/StatCard";
import { formatNumber, useLang } from "../i18n";
import api from "../services/api";

const STAT_FIELDS = [
  { field: "users_total", key: "dash.usersTotal" },
  { field: "users_today", key: "dash.usersToday" },
  { field: "downloads_total", key: "dash.downloadsTotal" },
  { field: "downloads_today", key: "dash.downloadsToday" },
  { field: "active_subscriptions", key: "dash.activeSubscriptions" },
  { field: "revenue_total", key: "dash.revenueTotal" },
  { field: "revenue_today", key: "dash.revenueToday" },
  { field: "queue_length", key: "dash.queueLength", accent: true },
];

export default function Dashboard() {
  const { locale, t } = useLang();
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    // Fetch both endpoints in parallel; keep whichever succeeds.
    const [statsRes, healthRes] = await Promise.allSettled([
      api.get("/admin/dashboard/stats"),
      api.get("/admin/system/health"),
    ]);
    if (statsRes.status === "fulfilled") setStats(statsRes.value.data);
    if (healthRes.status === "fulfilled") setHealth(healthRes.value.data);
    if (statsRes.status === "rejected" && healthRes.status === "rejected") {
      setError(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byStatus = stats && stats.downloads_by_status ? stats.downloads_by_status : null;

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.dashboard")}</h1>
        <button type="button" className="btn btn--ghost" onClick={load} disabled={loading}>
          {t("common.refresh")}
        </button>
      </div>

      {loading && <div className="page-note">{t("common.loading")}</div>}

      {!loading && error && (
        <div className="page-note page-note--error">
          {t("common.error")}{" "}
          <button type="button" className="btn btn--ghost" onClick={load}>
            {t("common.retry")}
          </button>
        </div>
      )}

      {!loading && stats && (
        <div className="stats-grid">
          {STAT_FIELDS.map(({ field, key, accent }) => (
            <StatCard
              key={field}
              label={t(key)}
              value={formatNumber(locale, stats[field])}
              accent={accent}
            />
          ))}
        </div>
      )}

      {!loading && byStatus && Object.keys(byStatus).length > 0 && (
        <section className="panel">
          <h2 className="panel__title">{t("dash.byStatus")}</h2>
          <div className="chip-row">
            {Object.entries(byStatus).map(([status, count]) => (
              <span key={status} className="chip">
                <span className="chip__label">{t(`status.${status}`)}</span>
                <span className="chip__value">{formatNumber(locale, count)}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {!loading && health && (
        <section className="panel">
          <h2 className="panel__title">{t("dash.health")}</h2>
          <div className="chip-row">
            <HealthBadge label={t("health.api")} status={health.api} />
            <HealthBadge label={t("health.database")} status={health.database} />
            <HealthBadge label={t("health.redis")} status={health.redis} />
            {health.version && (
              <span className="chip">
                <span className="chip__label">{t("dash.version")}</span>
                <span className="chip__value" dir="ltr">
                  {health.version}
                </span>
              </span>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
