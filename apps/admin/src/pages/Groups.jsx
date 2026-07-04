import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatDate, formatNumber, useLang } from "../i18n";
import api from "../services/api";

const PAGE_SIZE = 20;

export default function Groups() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [editing, setEditing] = useState(null);
  const [limitInput, setLimitInput] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/admin/groups", {
        params: { page, page_size: PAGE_SIZE },
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleEnabled(group) {
    setBusyId(group.id);
    setItems((prev) =>
      prev.map((g) => (g.id === group.id ? { ...g, is_enabled: !g.is_enabled } : g))
    );
    try {
      await api.patch(`/admin/groups/${group.id}`, { is_enabled: !group.is_enabled });
      await load();
    } catch {
      setItems((prev) =>
        prev.map((g) => (g.id === group.id ? { ...g, is_enabled: group.is_enabled } : g))
      );
    } finally {
      setBusyId(null);
    }
  }

  function openEdit(group) {
    setEditing(group);
    setLimitInput(
      group.daily_limit === null || group.daily_limit === undefined
        ? ""
        : String(group.daily_limit)
    );
  }

  async function saveLimit(event) {
    event.preventDefault();
    setSaving(true);
    const raw = limitInput.trim();
    const value = raw === "" ? -1 : Number(raw);
    try {
      await api.patch(`/admin/groups/${editing.id}`, { daily_limit: value });
      setEditing(null);
      await load();
    } catch {
      // keep the modal open on failure
    } finally {
      setSaving(false);
    }
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns = [
    {
      key: "telegram_chat_id",
      title: t("groups.chatId"),
      render: (g) => <span dir="ltr">{g.telegram_chat_id}</span>,
    },
    {
      key: "title",
      title: t("groups.name"),
      render: (g) => g.title || t("common.dash"),
    },
    {
      key: "username",
      title: t("groups.username"),
      render: (g) => (g.username ? <span dir="ltr">@{g.username}</span> : t("common.dash")),
    },
    {
      key: "daily_limit",
      title: t("groups.dailyLimit"),
      render: (g) =>
        g.daily_limit === null || g.daily_limit === undefined || Number(g.daily_limit) < 0
          ? t("groups.unlimited")
          : formatNumber(locale, g.daily_limit),
    },
    {
      key: "downloads_today",
      title: t("groups.downloadsToday"),
      render: (g) => formatNumber(locale, g.downloads_today),
    },
    {
      key: "total_downloads",
      title: t("groups.totalDownloads"),
      render: (g) => formatNumber(locale, g.total_downloads),
    },
    {
      key: "is_enabled",
      title: t("common.status"),
      render: (g) => (
        <span className={"badge " + (g.is_enabled ? "badge--success" : "badge--danger")}>
          {g.is_enabled ? t("common.enabled") : t("common.disabled")}
        </span>
      ),
    },
    {
      key: "created_at",
      title: t("common.createdAt"),
      render: (g) => formatDate(locale, g.created_at),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (g) => (
        <div className="actions-cell">
          <button
            type="button"
            className={"btn btn--small " + (g.is_enabled ? "btn--danger" : "btn--success")}
            disabled={busyId === g.id}
            onClick={() => toggleEnabled(g)}
          >
            {g.is_enabled ? t("common.disabled") : t("common.enabled")}
          </button>
          <button type="button" className="btn btn--small" onClick={() => openEdit(g)}>
            {t("groups.editLimit")}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.groups")}</h1>
        <span className="page__meta">
          {t("common.total", { total: formatNumber(locale, total) })}
        </span>
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

      {editing && (
        <Modal title={t("groups.editLimit")} onClose={() => setEditing(null)}>
          <form className="modal__body" onSubmit={saveLimit}>
            <label className="field">
              <span className="field__label">{t("groups.dailyLimit")}</span>
              <input
                type="number"
                dir="ltr"
                value={limitInput}
                onChange={(e) => setLimitInput(e.target.value)}
              />
              <span className="field__hint">{t("groups.limitHint")}</span>
            </label>
            <div className="modal__actions">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setEditing(null)}
              >
                {t("common.cancel")}
              </button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? t("common.saving") : t("common.save")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
