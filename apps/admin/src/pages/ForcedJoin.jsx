import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatNumber, useLang } from "../i18n";
import api from "../services/api";

const EMPTY = { username: "", channel_id: "", title: "", is_active: true, sort_order: "" };

export default function ForcedJoin() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [form, setForm] = useState(null);
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/admin/forced-join");
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

  function openCreate() {
    setEditId(null);
    setFormError(false);
    setForm({ ...EMPTY });
  }

  function openEdit(c) {
    setEditId(c.id);
    setFormError(false);
    setForm({
      username: c.username || "",
      channel_id: c.channel_id ?? "",
      title: c.title || "",
      is_active: c.is_active !== false,
      sort_order: c.sort_order ?? "",
    });
  }

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setFormError(false);
    const payload = {
      username: form.username.trim().replace(/^@/, ""),
      channel_id: form.channel_id === "" ? null : form.channel_id,
      title: form.title.trim() || null,
      is_active: form.is_active,
      sort_order: form.sort_order === "" ? 0 : Number(form.sort_order),
    };
    try {
      if (editId) {
        await api.patch(`/admin/forced-join/${editId}`, payload);
      } else {
        await api.post("/admin/forced-join", payload);
      }
      setForm(null);
      await load();
    } catch {
      setFormError(true);
    } finally {
      setSaving(false);
    }
  }

  async function remove(c) {
    if (!window.confirm(t("common.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/forced-join/${c.id}`);
      await load();
    } catch {
      // ignore
    }
  }

  const columns = [
    {
      key: "username",
      title: t("fj.username"),
      render: (c) => (c.username ? <span dir="ltr">@{c.username}</span> : t("common.dash")),
    },
    {
      key: "channel_id",
      title: t("fj.channelId"),
      render: (c) =>
        c.channel_id ? <span dir="ltr">{c.channel_id}</span> : t("common.dash"),
    },
    {
      key: "title",
      title: t("fj.title"),
      render: (c) => c.title || t("common.dash"),
    },
    {
      key: "sort_order",
      title: t("fj.sortOrder"),
      render: (c) => formatNumber(locale, c.sort_order),
    },
    {
      key: "is_active",
      title: t("common.status"),
      render: (c) => (
        <span className={"badge " + (c.is_active ? "badge--success" : "badge--neutral")}>
          {c.is_active ? t("common.active") : t("common.inactive")}
        </span>
      ),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (c) => (
        <div className="actions-cell">
          <button type="button" className="btn btn--small" onClick={() => openEdit(c)}>
            {t("common.edit")}
          </button>
          <button
            type="button"
            className="btn btn--small btn--danger"
            onClick={() => remove(c)}
          >
            {t("common.delete")}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.forcedJoin")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("fj.new")}
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

      {!loading && !error && <Table columns={columns} rows={items} />}

      {form && (
        <Modal title={editId ? t("fj.edit") : t("fj.new")} onClose={() => setForm(null)}>
          <form className="modal__body" onSubmit={submit}>
            <label className="field">
              <span className="field__label">{t("fj.username")}</span>
              <input
                type="text"
                dir="ltr"
                required
                placeholder="channel_username"
                value={form.username}
                onChange={(e) => set("username", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("fj.channelId")}</span>
              <input
                type="text"
                dir="ltr"
                value={form.channel_id}
                onChange={(e) => set("channel_id", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("fj.title")}</span>
              <input
                type="text"
                value={form.title}
                onChange={(e) => set("title", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("fj.sortOrder")}</span>
              <input
                type="number"
                dir="ltr"
                value={form.sort_order}
                onChange={(e) => set("sort_order", e.target.value)}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
              />
              <span>{t("common.active")}</span>
            </label>

            {formError && <div className="form-error">{t("common.saveFailed")}</div>}

            <div className="modal__actions">
              <button type="button" className="btn btn--ghost" onClick={() => setForm(null)}>
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
