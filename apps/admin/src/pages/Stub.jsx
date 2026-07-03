import { useLang } from "../i18n";

// Generic "coming soon" page for sections that only exist as sidebar entries.
// titleKey is an i18n key (e.g. "nav.groups").
export default function Stub({ titleKey }) {
  const { t } = useLang();
  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{t(titleKey)}</h1>
      </div>
      <div className="stub-card">
        <div className="stub-card__badge">{t("common.comingSoon")}</div>
        <p className="stub-card__text">{t("common.comingSoonDesc")}</p>
      </div>
    </div>
  );
}
