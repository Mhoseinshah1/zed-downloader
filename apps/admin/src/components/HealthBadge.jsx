import { useLang } from "../i18n";

// Colored status badge for system health checks: ok / error / unknown.
export default function HealthBadge({ label, status }) {
  const { t } = useLang();
  const normalized = status === "ok" ? "ok" : status ? "error" : "unknown";
  return (
    <span className={`health-badge health-badge--${normalized}`}>
      <span className="health-badge__dot" aria-hidden="true" />
      <span className="health-badge__label">{label}</span>
      <span className="health-badge__status">{t(`health.${normalized}`)}</span>
    </span>
  );
}
