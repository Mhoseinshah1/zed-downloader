import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { formatNumber, useLang } from "../i18n";
import api from "../services/api";

const EMPTY = {
  name: "",
  slug: "",
  platform_id: "",
  provider_type: "ytdlp",
  api_key: "",
  base_url: "",
  priority: "",
  timeout: "",
  settings: "",
  is_active: true,
};

export default function Providers() {
  const { locale, t } = useLang();
  const [items, setItems] = useState([]);
  const [platforms, setPlatforms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [form, setForm] = useState(null);
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null); // i18n key or null

  // Per-row action state.
  const [busy, setBusy] = useState({}); // id -> "test" | "balance"
  const [results, setResults] = useState({}); // id -> { ok, text }

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const [provRes, platRes] = await Promise.allSettled([
      api.get("/admin/providers"),
      api.get("/admin/platforms"),
    ]);
    if (platRes.status === "fulfilled") {
      setPlatforms(platRes.value.data.items || []);
    }
    if (provRes.status === "fulfilled") {
      setItems(provRes.value.data.items || []);
    } else {
      setError(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function platformName(id) {
    if (id === null || id === undefined || id === "") return t("common.dash");
    const p = platforms.find((x) => x.id === id);
    return p ? p.name : `#${id}`;
  }

  function openCreate() {
    setEditId(null);
    setFormError(null);
    setForm({ ...EMPTY });
  }

  function openEdit(p) {
    setEditId(p.id);
    setFormError(null);
    setForm({
      name: p.name || "",
      slug: p.slug || "",
      platform_id: p.platform_id ?? "",
      provider_type: p.provider_type || "ytdlp",
      api_key: "", // write-only: never populate from server
      base_url: p.base_url || "",
      priority: p.priority ?? "",
      timeout: p.timeout ?? "",
      settings:
        p.settings && typeof p.settings === "object"
          ? JSON.stringify(p.settings, null, 2)
          : p.settings || "",
      is_active: p.is_active !== false,
    });
  }

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setFormError(null);

    let parsedSettings;
    const rawSettings = form.settings.trim();
    if (rawSettings) {
      try {
        parsedSettings = JSON.parse(rawSettings);
      } catch {
        setFormError("providers.invalidJson");
        return;
      }
    }

    const payload = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      platform_id: form.platform_id === "" ? null : Number(form.platform_id),
      provider_type: form.provider_type,
      base_url: form.base_url.trim() || null,
      priority: form.priority === "" ? 0 : Number(form.priority),
      timeout: form.timeout === "" ? null : Number(form.timeout),
      is_active: form.is_active,
    };
    if (rawSettings) payload.settings = parsedSettings;
    // Only send api_key when provided (write-only; blank keeps existing).
    if (form.api_key.trim()) payload.api_key = form.api_key.trim();

    setSaving(true);
    try {
      if (editId) {
        await api.patch(`/admin/providers/${editId}`, payload);
      } else {
        await api.post("/admin/providers", payload);
      }
      setForm(null);
      await load();
    } catch {
      setFormError("common.saveFailed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(p) {
    if (!window.confirm(t("common.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/providers/${p.id}`);
      await load();
    } catch {
      // ignore
    }
  }

  async function runTest(p) {
    setBusy((b) => ({ ...b, [p.id]: "test" }));
    setResults((r) => ({ ...r, [p.id]: null }));
    try {
      const { data } = await api.post(`/admin/providers/${p.id}/test`);
      if (data && data.ok) {
        setResults((r) => ({ ...r, [p.id]: { ok: true, text: t("providers.testOk") } }));
      } else {
        setResults((r) => ({
          ...r,
          [p.id]: { ok: false, text: (data && data.error) || t("providers.testFailed") },
        }));
      }
    } catch {
      setResults((r) => ({ ...r, [p.id]: { ok: false, text: t("providers.testFailed") } }));
    } finally {
      setBusy((b) => ({ ...b, [p.id]: null }));
    }
  }

  async function checkBalance(p) {
    setBusy((b) => ({ ...b, [p.id]: "balance" }));
    setResults((r) => ({ ...r, [p.id]: null }));
    try {
      const { data } = await api.get(`/admin/providers/${p.id}/balance`);
      if (data && data.supported === false) {
        setResults((r) => ({
          ...r,
          [p.id]: { ok: false, text: t("providers.balanceUnsupported") },
        }));
      } else {
        const rest = { ...data };
        delete rest.supported;
        delete rest.ok;
        const text = Object.keys(rest).length
          ? Object.entries(rest)
              .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
              .join("  ")
          : t("providers.testOk");
        setResults((r) => ({ ...r, [p.id]: { ok: data.ok !== false, text } }));
      }
    } catch {
      setResults((r) => ({ ...r, [p.id]: { ok: false, text: t("common.error") } }));
    } finally {
      setBusy((b) => ({ ...b, [p.id]: null }));
    }
  }

  const columns = [
    { key: "name", title: t("providers.name") },
    {
      key: "slug",
      title: t("providers.slug"),
      render: (p) => <span dir="ltr">{p.slug}</span>,
    },
    {
      key: "platform_id",
      title: t("providers.platform"),
      render: (p) => platformName(p.platform_id),
    },
    {
      key: "provider_type",
      title: t("providers.type"),
      render: (p) => <span dir="ltr">{p.provider_type}</span>,
    },
    {
      key: "has_api_key",
      title: t("providers.apiKey"),
      render: (p) => (
        <span className={"badge " + (p.has_api_key ? "badge--success" : "badge--neutral")}>
          {p.has_api_key ? t("providers.hasKey") : t("providers.noKey")}
        </span>
      ),
    },
    {
      key: "priority",
      title: t("providers.priority"),
      render: (p) => formatNumber(locale, p.priority),
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
      render: (p) => {
        const res = results[p.id];
        return (
          <div className="actions-cell">
            <button type="button" className="btn btn--small" onClick={() => openEdit(p)}>
              {t("common.edit")}
            </button>
            <button
              type="button"
              className="btn btn--small"
              disabled={busy[p.id]}
              onClick={() => runTest(p)}
            >
              {busy[p.id] === "test" ? "…" : t("providers.test")}
            </button>
            <button
              type="button"
              className="btn btn--small"
              disabled={busy[p.id]}
              onClick={() => checkBalance(p)}
            >
              {busy[p.id] === "balance" ? "…" : t("providers.balance")}
            </button>
            <button
              type="button"
              className="btn btn--small btn--danger"
              onClick={() => remove(p)}
            >
              {t("common.delete")}
            </button>
            {res && (
              <span
                className={"result-note " + (res.ok ? "result-note--ok" : "result-note--err")}
                dir="ltr"
              >
                {res.text}
              </span>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t("nav.providers")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("providers.new")}
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
          title={editId ? t("providers.edit") : t("providers.new")}
          onClose={() => setForm(null)}
        >
          <form className="modal__body" onSubmit={submit}>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("providers.name")}</span>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">{t("providers.slug")}</span>
                <input
                  type="text"
                  dir="ltr"
                  required
                  value={form.slug}
                  onChange={(e) => set("slug", e.target.value)}
                />
              </label>
            </div>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("providers.platform")}</span>
                <select
                  value={form.platform_id}
                  onChange={(e) => set("platform_id", e.target.value)}
                >
                  <option value="">{t("providers.anyPlatform")}</option>
                  {platforms.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">{t("providers.type")}</span>
                <select
                  value={form.provider_type}
                  onChange={(e) => set("provider_type", e.target.value)}
                >
                  <option value="ytdlp">ytdlp</option>
                  <option value="apify">apify</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span className="field__label">{t("providers.apiKey")}</span>
              <input
                type="password"
                dir="ltr"
                autoComplete="new-password"
                value={form.api_key}
                onChange={(e) => set("api_key", e.target.value)}
              />
              {editId && <span className="field__hint">{t("providers.apiKeyHint")}</span>}
            </label>
            <label className="field">
              <span className="field__label">{t("providers.baseUrl")}</span>
              <input
                type="url"
                dir="ltr"
                value={form.base_url}
                onChange={(e) => set("base_url", e.target.value)}
              />
            </label>
            <div className="form-row">
              <label className="field">
                <span className="field__label">{t("providers.priority")}</span>
                <input
                  type="number"
                  dir="ltr"
                  value={form.priority}
                  onChange={(e) => set("priority", e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">{t("providers.timeout")}</span>
                <input
                  type="number"
                  dir="ltr"
                  value={form.timeout}
                  onChange={(e) => set("timeout", e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span className="field__label">{t("providers.settings")}</span>
              <textarea
                dir="ltr"
                className="mono"
                placeholder="{}"
                value={form.settings}
                onChange={(e) => set("settings", e.target.value)}
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

            {formError && <div className="form-error">{t(formError)}</div>}

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
