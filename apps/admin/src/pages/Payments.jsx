import { useCallback, useEffect, useState } from "react";
import StatusBadge from "../components/StatusBadge";
import Table from "../components/Table";
import { formatDate, formatNumber, useLang } from "../i18n";
import api from "../services/api";

const PAGE_SIZE = 20;
const STATUSES = ["pending", "paid", "completed", "failed", "refunded", "cancelled", "expired"];

export default function Payments() {
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
      const { data } = await api.get("/admin/payments", { params });
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
    { key: "id", title: "#", render: (p) => <span dir="ltr">{p.id}</span> },
    {
      key: "user",
      title: t("payments.user"),
      render: (p) => (
        <span dir="ltr">{p.user_telegram_id || p.user_id || t("common.dash")}</span>
      ),
    },
    {
      key: "plan_name",
      title: t("payments.plan"),
      render: (p) => p.plan_name || (p.plan_id ? `#${p.plan_id}` : t("common.dash")),
    },
    {
      key: "gateway",
      title: t("payments.gateway"),
      render: (p) => (p.gateway ? <span dir="ltr">{p.gateway}</span> : t("common.dash")),
    },
    {
      key: "amount",
      title: t("payments.amount"),
      render: (p) => (
        <span dir="ltr">
          {formatNumber(locale, p.amount)} {p.currency || ""}
        </span>
      ),
    },
    {
      key: "status",
      title: t("common.status"),
      render: (p) => <StatusBadge status={p.status} prefix="payStatus" />,
    },
    {
      key: "transaction_id",
      title: t("payments.transactionId"),
      render: (p) =>
        p.transaction_id ? (
          <span className="trunc-cell mono" dir="ltr" title={p.transaction_id}>
            {p.transaction_id}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "authority",
      title: t("payments.authority"),
      render: (p) =>
        p.authority ? (
          <span className="trunc-cell mono" dir="ltr" title={p.authority}>
            {p.authority}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "paid_at",
      title: t("payments.paidAt"),
      render: (p) => formatDate(locale, p.paid_at),
    },
    {
      key: "created_at",
      title: t("common.createdAt"),
      render: (p) => formatDate(locale, p.created_at),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.payments")}</h1>
        <span className="page__meta">
          {t("common.total", { total: formatNumber(locale, total) })}
        </span>
      </div>

      <div className="toolbar">
        <label className="field-inline">
          <span className="field__label">{t("common.status")}</span>
          <select value={status} onChange={onFilterChange}>
            <option value="">{t("common.all")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`payStatus.${s}`)}
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
