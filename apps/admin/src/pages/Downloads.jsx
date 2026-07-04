import { useCallback, useEffect, useState } from "react";
import StatusBadge from "../components/StatusBadge";
import Table from "../components/Table";
import { formatDate, formatNumber, useLang } from "../i18n";
import api from "../services/api";

const PAGE_SIZE = 20;
const STATUSES = [
  "queued",
  "processing",
  "downloading",
  "completed",
  "failed",
  "cancelled",
  "denied",
];

function formatSize(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return "—";
  const n = Number(bytes);
  if (n <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let value = n;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function Downloads() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (status) params.status = status;
      const { data } = await api.get("/admin/downloads", { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    load();
  }, [load]);

  function onFilterChange(e) {
    setPage(1);
    setStatus(e.target.value);
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns = [
    { key: "id", title: "#", render: (d) => <span dir="ltr">{d.id}</span> },
    {
      key: "user_id",
      title: t("downloads.user"),
      render: (d) => <span dir="ltr">{d.user_id ?? t("common.dash")}</span>,
    },
    {
      key: "url",
      title: t("downloads.url"),
      render: (d) =>
        d.url ? (
          <a
            className="trunc-cell"
            href={d.url}
            target="_blank"
            rel="noreferrer"
            dir="ltr"
            title={d.url}
          >
            {d.url}
          </a>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "status",
      title: t("common.status"),
      render: (d) => <StatusBadge status={d.status} prefix="status" />,
    },
    {
      key: "file_name",
      title: t("downloads.fileName"),
      render: (d) =>
        d.file_name ? (
          <span className="trunc-cell" dir="ltr" title={d.file_name}>
            {d.file_name}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "file_size",
      title: t("downloads.fileSize"),
      render: (d) => <span dir="ltr">{formatSize(d.file_size)}</span>,
    },
    {
      key: "file_type",
      title: t("downloads.fileType"),
      render: (d) => (d.file_type ? <span dir="ltr">{d.file_type}</span> : t("common.dash")),
    },
    {
      key: "error_code",
      title: t("downloads.error"),
      render: (d) =>
        d.error_code ? (
          <span className="badge badge--danger" dir="ltr">
            {d.error_code}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "created_at",
      title: t("common.createdAt"),
      render: (d) => formatDate(locale, d.created_at),
    },
    {
      key: "completed_at",
      title: t("downloads.completedAt"),
      render: (d) => formatDate(locale, d.completed_at),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.downloads")}</h1>
        <span className="page__meta">
          {t("common.total", { total: formatNumber(locale, total) })}
        </span>
      </div>

      <div className="toolbar">
        <label className="field-inline">
          <span className="field__label">{t("common.status")}</span>
          <select value={status} onChange={onFilterChange}>
            <option value="">{t("downloads.allStatuses")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        </label>
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

      {!loading && !error && (
        <>
          <Table columns={columns} rows={items} />
          <div className="pager">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              {t("pager.prev")}
            </button>
            <span className="pager__info">
              {t("pager.pageOf", {
                page: formatNumber(locale, page),
                pages: formatNumber(locale, pages),
              })}
            </span>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= pages}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
            >
              {t("pager.next")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
