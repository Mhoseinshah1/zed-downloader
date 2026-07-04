import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatNumber, useLang } from "../i18n";
import api from "../services/api";

const EMPTY = {
  name: "",
  description: "",
  price: "",
  currency: "IRR",
  duration_days: "",
  download_limit: "",
  scope: "user",
  is_active: true,
  sort_order: "",
};

export default function Plans() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [form, setForm] = useState(null); // null = closed; object = open
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/admin/plans");
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
      description: p.description || "",
      price: p.price ?? "",
      currency: p.currency || "IRR",
      duration_days: p.duration_days ?? "",
      download_limit: p.download_limit ?? "",
      scope: p.scope || "user",
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
      description: form.description.trim() || null,
      price: Number(form.price),
      currency: form.currency.trim() || "IRR",
      duration_days: Number(form.duration_days),
      download_limit: form.download_limit === "" ? null : Number(form.download_limit),
      scope: form.scope,
      is_active: form.is_active,
      sort_order: form.sort_order === "" ? 0 : Number(form.sort_order),
    };
    try {
      if (editId) {
        await api.patch(`/admin/plans/${editId}`, payload);
      } else {
        await api.post("/admin/plans", payload);
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
      await api.delete(`/admin/plans/${p.id}`);
      await load();
    } catch {
      // ignore; row stays
    }
  }

  const columns = [
    { key: "name", title: t("plans.name") },
    {
      key: "price",
      title: t("plans.price"),
      render: (p) => (
        <span dir="ltr">
          {formatNumber(locale, p.price)} {p.currency || ""}
        </span>
      ),
    },
    {
      key: "duration_days",
      title: t("plans.duration"),
      render: (p) => formatNumber(locale, p.duration_days),
    },
    {
      key: "download_limit",
      title: t("plans.downloadLimit"),
      render: (p) =>
        p.download_limit === null || p.download_limit === undefined
          ? t("groups.unlimited")
          : formatNumber(locale, p.download_limit),
    },
    {
      key: "scope",
      title: t("plans.scope"),
      render: (p) => t(p.scope === "group" ? "plans.scopeGroup" : "plans.scopeUser"),
    },
    {
      key: "sort_order",
      title: t("plans.sortOrder"),
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
        <h1 className="page__title">{t("nav.plans")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("plans.new")}
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
          title={editId ? t("plans.edit") : t("plans.new")}
          onClose={() => setForm(null)}
        >
          <form className="modal__body" onSubmit={submit}>
            <label className="field">
              <span className="field__label">{t("plans.name")}</span>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("plans.description")}</span>
              <textarea
                value={form.description}
                onChange={(e) => set("description", e.target.value)}
              />
            </label>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("plans.price")}</span>
                <input
                  type="number"
                  dir="ltr"
                  required
                  value={form.price}
                  onChange={(e) => set("price", e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">{t("plans.currency")}</span>
                <input
                  type="text"
                  dir="ltr"
                  value={form.currency}
                  onChange={(e) => set("currency", e.target.value)}
                />
              </label>
            </div>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("plans.duration")}</span>
                <input
                  type="number"
                  dir="ltr"
                  required
                  value={form.duration_days}
                  onChange={(e) => set("duration_days", e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">{t("plans.downloadLimit")}</span>
                <input
                  type="number"
                  dir="ltr"
                  value={form.download_limit}
                  onChange={(e) => set("download_limit", e.target.value)}
                />
              </label>
            </div>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("plans.scope")}</span>
                <select value={form.scope} onChange={(e) => set("scope", e.target.value)}>
                  <option value="user">{t("plans.scopeUser")}</option>
                  <option value="group">{t("plans.scopeGroup")}</option>
                </select>
              </label>
              <label className="field">
                <span className="field__label">{t("plans.sortOrder")}</span>
                <input
                  type="number"
                  dir="ltr"
                  value={form.sort_order}
                  onChange={(e) => set("sort_order", e.target.value)}
                />
              </label>
            </div>
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
