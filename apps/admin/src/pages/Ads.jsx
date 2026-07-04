import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatDate, formatNumber, useLang } from "../i18n";
import api from "../services/api";

const EMPTY = { title: "", content: "", media_url: "", is_active: true, weight: "" };

export default function Ads() {
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
      const { data } = await api.get("/admin/ads");
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

  function openEdit(a) {
    setEditId(a.id);
    setFormError(false);
    setForm({
      title: a.title || "",
      content: a.content || "",
      media_url: a.media_url || "",
      is_active: a.is_active !== false,
      weight: a.weight ?? "",
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
      title: form.title.trim(),
      content: form.content,
      media_url: form.media_url.trim() || null,
      is_active: form.is_active,
      weight: form.weight === "" ? 1 : Number(form.weight),
    };
    try {
      if (editId) {
        await api.patch(`/admin/ads/${editId}`, payload);
      } else {
        await api.post("/admin/ads", payload);
      }
      setForm(null);
      await load();
    } catch {
      setFormError(true);
    } finally {
      setSaving(false);
    }
  }

  async function remove(a) {
    if (!window.confirm(t("common.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/ads/${a.id}`);
      await load();
    } catch {
      // ignore
    }
  }

  const columns = [
    { key: "title", title: t("ads.adTitle"), render: (a) => a.title || t("common.dash") },
    {
      key: "content",
      title: t("ads.content"),
      render: (a) =>
        a.content ? (
          <span className="trunc-cell" title={a.content}>
            {a.content}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "media_url",
      title: t("ads.mediaUrl"),
      render: (a) =>
        a.media_url ? (
          <a
            className="trunc-cell"
            href={a.media_url}
            target="_blank"
            rel="noreferrer"
            dir="ltr"
            title={a.media_url}
          >
            {a.media_url}
          </a>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "weight",
      title: t("ads.weight"),
      render: (a) => formatNumber(locale, a.weight),
    },
    {
      key: "is_active",
      title: t("common.status"),
      render: (a) => (
        <span className={"badge " + (a.is_active ? "badge--success" : "badge--neutral")}>
          {a.is_active ? t("common.active") : t("common.inactive")}
        </span>
      ),
    },
    {
      key: "created_at",
      title: t("common.createdAt"),
      render: (a) => formatDate(locale, a.created_at),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (a) => (
        <div className="actions-cell">
          <button type="button" className="btn btn--small" onClick={() => openEdit(a)}>
            {t("common.edit")}
          </button>
          <button
            type="button"
            className="btn btn--small btn--danger"
            onClick={() => remove(a)}
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
        <h1 className="page__title">{t("nav.ads")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("ads.new")}
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
        <Modal title={editId ? t("ads.edit") : t("ads.new")} onClose={() => setForm(null)}>
          <form className="modal__body" onSubmit={submit}>
            <label className="field">
              <span className="field__label">{t("ads.adTitle")}</span>
              <input
                type="text"
                required
                value={form.title}
                onChange={(e) => set("title", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("ads.content")}</span>
              <textarea
                required
                value={form.content}
                onChange={(e) => set("content", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("ads.mediaUrl")}</span>
              <input
                type="url"
                dir="ltr"
                value={form.media_url}
                onChange={(e) => set("media_url", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("ads.weight")}</span>
              <input
                type="number"
                dir="ltr"
                value={form.weight}
                onChange={(e) => set("weight", e.target.value)}
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
