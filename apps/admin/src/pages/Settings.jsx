import { useCallback, useEffect, useState } from "react";
import Table from "../components/Table";
import { useLang } from "../i18n";
import api from "../services/api";

export default function Settings() {
  const { t } = useLang();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [editKey, setEditKey] = useState(null);
  const [draft, setDraft] = useState("");
  const [savingKey, setSavingKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/admin/settings");
      setItems(data.items || []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function startEdit(row) {
    setEditKey(row.key);
    setDraft(row.value == null ? "" : String(row.value));
  }

  function cancel() {
    setEditKey(null);
    setDraft("");
  }

  async function save(row) {
    setSavingKey(row.key);
    try {
      await api.put(`/admin/settings/${encodeURIComponent(row.key)}`, { value: draft });
      setEditKey(null);
      setDraft("");
      await load();
    } catch {
      // keep editing on failure
    } finally {
      setSavingKey(null);
    }
  }

  const columns = [
    {
      key: "key",
      title: t("settings.key"),
      render: (r) => (
        <span className="mono" dir="ltr">
          {r.key}
        </span>
      ),
    },
    {
      key: "value",
      title: t("settings.value"),
      render: (r) =>
        editKey === r.key ? (
          <input
            type="text"
            dir="ltr"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
          />
        ) : (
          <span className="trunc-cell" dir="ltr" title={r.value}>
            {r.value == null || r.value === "" ? t("common.dash") : String(r.value)}
          </span>
        ),
    },
    {
      key: "description",
      title: t("settings.description"),
      render: (r) => r.description || t("common.dash"),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (r) =>
        editKey === r.key ? (
          <div className="actions-cell">
            <button
              type="button"
              className="btn btn--small btn--primary"
              disabled={savingKey === r.key}
              onClick={() => save(r)}
            >
              {savingKey === r.key ? t("common.saving") : t("common.save")}
            </button>
            <button type="button" className="btn btn--small btn--ghost" onClick={cancel}>
              {t("common.cancel")}
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => startEdit(r)}>
            {t("common.edit")}
          </button>
        ),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.settings")}</h1>
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

      {!loading && !error && <Table columns={columns} rows={items} rowKey="key" />}
    </div>
  );
}
