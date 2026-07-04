import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatNumber, useLang } from "../i18n";
import api from "../services/api";

const EMPTY = { name: "", slug: "", url_regex: "", is_active: true, sort_order: "" };

export default function Platforms() {
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
      const { data } = await api.get("/admin/platforms");
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

  function openEdit(p) {
    setEditId(p.id);
    setFormError(false);
    setForm({
      name: p.name || "",
      slug: p.slug || "",
      url_regex: p.url_regex || "",
      is_active: p.is_active !== false,
      sort_order: p.sort_order ?? "",
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
      name: form.name.trim(),
      slug: form.slug.trim(),
      url_regex: form.url_regex.trim(),
      is_active: form.is_active,
      sort_order: form.sort_order === "" ? 0 : Number(form.sort_order),
    };
    try {
      if (editId) {
        await api.patch(`/admin/platforms/${editId}`, payload);
      } else {
        await api.post("/admin/platforms", payload);
      }
      setForm(null);
      await load();
    } catch {
      setFormError(true);
    } finally {
      setSaving(false);
    }
  }

  async function remove(p) {
    if (!window.confirm(t("common.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/platforms/${p.id}`);
      await load();
    } catch {
      // ignore
    }
  }

  const columns = [
    { key: "name", title: t("platforms.name") },
    {
      key: "slug",
      title: t("platforms.slug"),
      render: (p) => <span dir="ltr">{p.slug}</span>,
    },
    {
      key: "url_regex",
      title: t("platforms.urlRegex"),
      render: (p) =>
        p.url_regex ? (
          <span className="trunc-cell mono" dir="ltr" title={p.url_regex}>
            {p.url_regex}
          </span>
        ) : (
          t("common.dash")
        ),
    },
    {
      key: "sort_order",
      title: t("platforms.sortOrder"),
      render: (p) => formatNumber(locale, p.sort_order),
    },
    {
      key: "is_active",
      title: t("common.status"),
      render: (p) => (
        <span className={"badge " + (p.is_active ? "badge--success" : "badge--neutral")}>
          {p.is_active ? t("common.active") : t("common.inactive")}
        </span>
      ),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (p) => (
        <div className="actions-cell">
          <button type="button" className="btn btn--small" onClick={() => openEdit(p)}>
            {t("common.edit")}
          </button>
          <button
            type="button"
            className="btn btn--small btn--danger"
            onClick={() => remove(p)}
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
        <h1 className="page__title">{t("nav.platforms")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("platforms.new")}
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
        <Modal
          title={editId ? t("platforms.edit") : t("platforms.new")}
          onClose={() => setForm(null)}
        >
          <form className="modal__body" onSubmit={submit}>
            <label className="field">
              <span className="field__label">{t("platforms.name")}</span>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("platforms.slug")}</span>
              <input
                type="text"
                dir="ltr"
                required
                value={form.slug}
                onChange={(e) => set("slug", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("platforms.urlRegex")}</span>
              <input
                type="text"
                dir="ltr"
                required
                className="mono"
                value={form.url_regex}
                onChange={(e) => set("url_regex", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("platforms.sortOrder")}</span>
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
