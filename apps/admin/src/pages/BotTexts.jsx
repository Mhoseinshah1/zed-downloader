import { useCallback, useEffect, useState } from "react";
import Modal from "../components/Modal";
import Table from "../components/Table";
import { SUPPORTED_LANGS, useLang } from "../i18n";
import api from "../services/api";

const LANG_CODES = Object.keys(SUPPORTED_LANGS);

export default function BotTexts() {
  const { t } = useLang();
  const [items, setItems] = useState([]);
  const [langFilter, setLangFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [editId, setEditId] = useState(null);
  const [draft, setDraft] = useState("");
  const [savingId, setSavingId] = useState(null);

  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = {};
      if (langFilter) params.lang = langFilter;
      const { data } = await api.get("/admin/bot-texts", { params });
      setItems(data.items || []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [langFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function startEdit(row) {
    setEditId(row.id);
    setDraft(row.value == null ? "" : String(row.value));
  }

  function cancelEdit() {
    setEditId(null);
    setDraft("");
  }

  async function saveValue(row) {
    setSavingId(row.id);
    try {
      await api.patch(`/admin/bot-texts/${row.id}`, { value: draft });
      setEditId(null);
      setDraft("");
      await load();
    } catch {
      // keep editing
    } finally {
      setSavingId(null);
    }
  }

  async function remove(row) {
    if (!window.confirm(t("common.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/bot-texts/${row.id}`);
      await load();
    } catch {
      // ignore
    }
  }

  function openCreate() {
    setFormError(false);
    setForm({ key: "", lang: LANG_CODES[0] || "fa", value: "" });
  }

  function setField(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function submitCreate(event) {
    event.preventDefault();
    setSaving(true);
    setFormError(false);
    try {
      await api.post("/admin/bot-texts", {
        key: form.key.trim(),
        lang: form.lang,
        value: form.value,
      });
      setForm(null);
      await load();
    } catch {
      setFormError(true);
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    {
      key: "key",
      title: t("botTexts.key"),
      render: (r) => (
        <span className="mono" dir="ltr">
          {r.key}
        </span>
      ),
    },
    {
      key: "lang",
      title: t("botTexts.lang"),
      render: (r) => <span dir="ltr">{r.lang}</span>,
    },
    {
      key: "value",
      title: t("botTexts.value"),
      render: (r) =>
        editId === r.id ? (
          <textarea value={draft} autoFocus onChange={(e) => setDraft(e.target.value)} />
        ) : (
          <span className="trunc-cell" title={r.value}>
            {r.value == null || r.value === "" ? t("common.dash") : String(r.value)}
          </span>
        ),
    },
    {
      key: "actions",
      title: t("common.actions"),
      render: (r) =>
        editId === r.id ? (
          <div className="actions-cell">
            <button
              type="button"
              className="btn btn--small btn--primary"
              disabled={savingId === r.id}
              onClick={() => saveValue(r)}
            >
              {savingId === r.id ? t("common.saving") : t("common.save")}
            </button>
            <button type="button" className="btn btn--small btn--ghost" onClick={cancelEdit}>
              {t("common.cancel")}
            </button>
          </div>
        ) : (
          <div className="actions-cell">
            <button type="button" className="btn btn--small" onClick={() => startEdit(r)}>
              {t("common.edit")}
            </button>
            <button
              type="button"
              className="btn btn--small btn--danger"
              onClick={() => remove(r)}
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
        <h1 className="page__title">{t("nav.botTexts")}</h1>
        <button type="button" className="btn btn--primary" onClick={openCreate}>
          {t("botTexts.new")}
        </button>
      </div>

      <div className="toolbar">
        <label className="field-inline">
          <span className="field__label">{t("botTexts.lang")}</span>
          <select value={langFilter} onChange={(e) => setLangFilter(e.target.value)}>
            <option value="">{t("botTexts.allLangs")}</option>
            {LANG_CODES.map((code) => (
              <option key={code} value={code}>
                {SUPPORTED_LANGS[code].label} ({code})
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

      {!loading && !error && <Table columns={columns} rows={items} />}

      {form && (
        <Modal title={t("botTexts.new")} onClose={() => setForm(null)}>
          <form className="modal__body" onSubmit={submitCreate}>
            <label className="field">
              <span className="field__label">{t("botTexts.key")}</span>
              <input
                type="text"
                dir="ltr"
                required
                className="mono"
                value={form.key}
                onChange={(e) => setField("key", e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{t("botTexts.lang")}</span>
              <select value={form.lang} onChange={(e) => setField("lang", e.target.value)}>
                {LANG_CODES.map((code) => (
                  <option key={code} value={code}>
                    {SUPPORTED_LANGS[code].label} ({code})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">{t("botTexts.value")}</span>
              <textarea
                required
                value={form.value}
                onChange={(e) => setField("value", e.target.value)}
              />
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
