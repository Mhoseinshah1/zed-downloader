import { useCallback, useEffect, useState } from "react";
import Table from "../components/Table";
import { formatDate, formatNumber, useLang } from "../i18n";
import api from "../services/api";

const PAGE_SIZE = 20;

export default function Users() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/admin/users", {
        params: { search, page, page_size: PAGE_SIZE },
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    load();
  }, [load]);

  function handleSearch(event) {
    event.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  }

  async function toggleBlock(user) {
    const action = user.is_blocked ? "unblock" : "block";
    setBusyId(user.id);
    // Optimistic flip; revert on failure, then re-sync from the server.
    setItems((prev) =>
      prev.map((u) => (u.id === user.id ? { ...u, is_blocked: !u.is_blocked } : u))
    );
    try {
      await api.post(`/admin/users/${user.id}/${action}`);
      await load();
    } catch {
      setItems((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, is_blocked: user.is_blocked } : u))
      );
    } finally {
      setBusyId(null);
    }
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns = [
    {
      key: "telegram_id",
      title: t("users.telegramId"),
      render: (u) => <span dir="ltr">{u.telegram_id}</span>,
    },
    {
      key: "username",
      title: t("users.username"),
      render: (u) => (u.username ? <span dir="ltr">@{u.username}</span> : t("common.dash")),
    },
    {
      key: "name",
      title: t("users.name"),
      render: (u) =>
        [u.first_name, u.last_name].filter(Boolean).join(" ") || t("common.dash"),
    },
    {
      key: "language",
      title: t("users.language"),
      render: (u) => <span dir="ltr">{u.language || t("common.dash")}</span>,
    },
    {
      key: "total_downloads",
      title: t("users.totalDownloads"),
      render: (u) => formatNumber(locale, u.total_downloads),
    },
    {
      key: "is_blocked",
      title: t("users.status"),
      render: (u) => (
        <span className={"badge " + (u.is_blocked ? "badge--danger" : "badge--success")}>
          {u.is_blocked ? t("users.blocked") : t("users.active")}
        </span>
      ),
    },
    {
      key: "created_at",
      title: t("users.createdAt"),
      render: (u) => formatDate(locale, u.created_at),
    },
    {
      key: "actions",
      title: t("users.actions"),
      render: (u) => (
        <button
          type="button"
          className={"btn btn--small " + (u.is_blocked ? "btn--success" : "btn--danger")}
          disabled={busyId === u.id}
          onClick={() => toggleBlock(u)}
        >
          {u.is_blocked ? t("users.unblock") : t("users.block")}
        </button>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.users")}</h1>
        <span className="page__meta">{t("users.total", { total: formatNumber(locale, total) })}</span>
      </div>

      <form className="search-bar" onSubmit={handleSearch}>
        <input
          type="text"
          value={searchInput}
          placeholder={t("users.searchPlaceholder")}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button type="submit" className="btn btn--primary">
          {t("users.searchBtn")}
        </button>
      </form>

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
          <Table columns={columns} rows={items} emptyText={t("users.empty")} />
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
