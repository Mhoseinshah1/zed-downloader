import { useLang } from "../i18n";

// Maps a status string to a badge color. Unknown statuses fall back to neutral.
const CLASS_MAP = {
  completed: "badge--success",
  paid: "badge--success",
  processing: "badge--warn",
  downloading: "badge--warn",
  queued: "badge--warn",
  pending: "badge--warn",
  failed: "badge--danger",
  denied: "badge--danger",
  cancelled: "badge--danger",
  canceled: "badge--danger",
  expired: "badge--danger",
  refunded: "badge--neutral",
};

// prefix is the i18n namespace for labels, e.g. "status" or "payStatus".
// When there is no translation, the raw status string is shown as-is.
export default function StatusBadge({ status, prefix = "status" }) {
  const { t } = useLang();
  if (!status) return <span>{t("common.dash")}</span>;
  const cls = CLASS_MAP[status] || "badge--neutral";
  const key = `${prefix}.${status}`;
  const label = t(key);
  return <span className={"badge " + cls}>{label === key ? status : label}</span>;
}
