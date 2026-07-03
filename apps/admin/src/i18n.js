// Lightweight i18n: fa (default) + en, structured so more languages can be
// added later by appending a dict + an entry in SUPPORTED_LANGS.
// NOTE: this file is plain .js (no JSX) so it works without the JSX transform.
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const LANG_STORAGE_KEY = "zed_admin_lang";
export const DEFAULT_LANG = "fa";

export const SUPPORTED_LANGS = {
  fa: { label: "فارسی", dir: "rtl", locale: "fa-IR" },
  en: { label: "English", dir: "ltr", locale: "en-US" },
  // NOTE: add the other 14 languages here later, e.g.:
  // ar: { label: "العربية", dir: "rtl", locale: "ar" },
};

const messages = {
  fa: {
    "app.title": "زد دانلودر",
    "app.subtitle": "پنل مدیریت",

    "nav.dashboard": "داشبورد",
    "nav.users": "کاربران",
    "nav.groups": "گروه‌ها",
    "nav.downloads": "دانلودها",
    "nav.plans": "پلن‌های اشتراک",
    "nav.payments": "پرداخت‌ها",
    "nav.platforms": "پلتفرم‌ها",
    "nav.providers": "سرویس‌دهنده‌ها",
    "nav.ads": "تبلیغات",
    "nav.forcedJoin": "عضویت اجباری",
    "nav.languages": "زبان‌ها",
    "nav.botTexts": "متن‌های ربات",
    "nav.broadcast": "پیام همگانی",
    "nav.admins": "مدیران",
    "nav.settings": "تنظیمات",
    "nav.backup": "پشتیبان‌گیری",
    "nav.update": "به‌روزرسانی",
    "nav.health": "سلامت سیستم",

    "login.title": "ورود به پنل مدیریت",
    "login.email": "ایمیل",
    "login.password": "رمز عبور",
    "login.submit": "ورود",
    "login.submitting": "در حال ورود…",
    "login.invalid": "ایمیل یا رمز عبور نادرست است.",
    "login.error": "خطا در برقراری ارتباط با سرور.",

    "common.loading": "در حال بارگذاری…",
    "common.error": "خطایی رخ داد.",
    "common.retry": "تلاش مجدد",
    "common.refresh": "به‌روزرسانی",
    "common.logout": "خروج",
    "common.comingSoon": "به‌زودی",
    "common.comingSoonDesc": "این بخش در نسخه‌های بعدی فعال می‌شود.",
    "common.dash": "—",

    "dash.usersTotal": "کل کاربران",
    "dash.usersToday": "کاربران امروز",
    "dash.downloadsTotal": "کل دانلودها",
    "dash.downloadsToday": "دانلودهای امروز",
    "dash.activeSubscriptions": "اشتراک‌های فعال",
    "dash.revenueTotal": "درآمد کل",
    "dash.revenueToday": "درآمد امروز",
    "dash.queueLength": "طول صف دانلود",
    "dash.byStatus": "دانلودها بر اساس وضعیت",
    "dash.health": "وضعیت سرویس‌ها",
    "dash.version": "نسخه",

    "health.api": "API",
    "health.database": "پایگاه داده",
    "health.redis": "ردیس",
    "health.ok": "سالم",
    "health.error": "خطا",
    "health.unknown": "نامشخص",

    "status.queued": "در صف",
    "status.processing": "در حال پردازش",
    "status.downloading": "در حال دانلود",
    "status.completed": "موفق",
    "status.failed": "ناموفق",
    "status.cancelled": "لغو شده",

    "users.searchPlaceholder": "جستجو بر اساس نام کاربری یا شناسه…",
    "users.searchBtn": "جستجو",
    "users.telegramId": "شناسه تلگرام",
    "users.username": "نام کاربری",
    "users.name": "نام",
    "users.language": "زبان",
    "users.totalDownloads": "دانلودها",
    "users.status": "وضعیت",
    "users.createdAt": "تاریخ عضویت",
    "users.actions": "عملیات",
    "users.blocked": "مسدود",
    "users.active": "فعال",
    "users.block": "مسدودسازی",
    "users.unblock": "رفع مسدودی",
    "users.total": "مجموع: {total}",

    "table.empty": "موردی یافت نشد.",

    "pager.prev": "قبلی",
    "pager.next": "بعدی",
    "pager.pageOf": "صفحه {page} از {pages}",
  },
  en: {
    "app.title": "Zed Downloader",
    "app.subtitle": "Admin Panel",

    "nav.dashboard": "Dashboard",
    "nav.users": "Users",
    "nav.groups": "Groups",
    "nav.downloads": "Downloads",
    "nav.plans": "Subscription Plans",
    "nav.payments": "Payments",
    "nav.platforms": "Platforms",
    "nav.providers": "Providers",
    "nav.ads": "Ads",
    "nav.forcedJoin": "Forced Join",
    "nav.languages": "Languages",
    "nav.botTexts": "Bot Texts",
    "nav.broadcast": "Broadcast",
    "nav.admins": "Admins",
    "nav.settings": "Settings",
    "nav.backup": "Backup",
    "nav.update": "Update",
    "nav.health": "System Health",

    "login.title": "Sign in to Admin Panel",
    "login.email": "Email",
    "login.password": "Password",
    "login.submit": "Sign in",
    "login.submitting": "Signing in…",
    "login.invalid": "Invalid email or password.",
    "login.error": "Failed to reach the server.",

    "common.loading": "Loading…",
    "common.error": "Something went wrong.",
    "common.retry": "Retry",
    "common.refresh": "Refresh",
    "common.logout": "Log out",
    "common.comingSoon": "Coming soon",
    "common.comingSoonDesc": "This section will be available in a future release.",
    "common.dash": "—",

    "dash.usersTotal": "Total users",
    "dash.usersToday": "Users today",
    "dash.downloadsTotal": "Total downloads",
    "dash.downloadsToday": "Downloads today",
    "dash.activeSubscriptions": "Active subscriptions",
    "dash.revenueTotal": "Total revenue",
    "dash.revenueToday": "Revenue today",
    "dash.queueLength": "Queue length",
    "dash.byStatus": "Downloads by status",
    "dash.health": "Service health",
    "dash.version": "Version",

    "health.api": "API",
    "health.database": "Database",
    "health.redis": "Redis",
    "health.ok": "OK",
    "health.error": "Error",
    "health.unknown": "Unknown",

    "status.queued": "Queued",
    "status.processing": "Processing",
    "status.downloading": "Downloading",
    "status.completed": "Completed",
    "status.failed": "Failed",
    "status.cancelled": "Cancelled",

    "users.searchPlaceholder": "Search by username or ID…",
    "users.searchBtn": "Search",
    "users.telegramId": "Telegram ID",
    "users.username": "Username",
    "users.name": "Name",
    "users.language": "Language",
    "users.totalDownloads": "Downloads",
    "users.status": "Status",
    "users.createdAt": "Joined",
    "users.actions": "Actions",
    "users.blocked": "Blocked",
    "users.active": "Active",
    "users.block": "Block",
    "users.unblock": "Unblock",
    "users.total": "Total: {total}",

    "table.empty": "Nothing found.",

    "pager.prev": "Previous",
    "pager.next": "Next",
    "pager.pageOf": "Page {page} of {pages}",
  },
};

export function translate(lang, key, vars) {
  const dict = messages[lang] || messages[DEFAULT_LANG];
  let text = dict[key];
  if (text === undefined) text = messages.en[key];
  if (text === undefined) text = key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

function getInitialLang() {
  const stored = localStorage.getItem(LANG_STORAGE_KEY);
  if (stored && SUPPORTED_LANGS[stored]) return stored;
  return DEFAULT_LANG;
}

const LangContext = createContext({
  lang: DEFAULT_LANG,
  dir: "rtl",
  locale: "fa-IR",
  setLang: () => {},
  t: (key) => key,
});

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getInitialLang);

  // Keep <html lang dir> in sync so the whole document flips direction.
  useEffect(() => {
    const meta = SUPPORTED_LANGS[lang];
    document.documentElement.setAttribute("lang", lang);
    document.documentElement.setAttribute("dir", meta.dir);
  }, [lang]);

  const setLang = useCallback((next) => {
    if (!SUPPORTED_LANGS[next]) return;
    localStorage.setItem(LANG_STORAGE_KEY, next);
    setLangState(next);
  }, []);

  const t = useCallback((key, vars) => translate(lang, key, vars), [lang]);

  const value = useMemo(() => {
    const meta = SUPPORTED_LANGS[lang];
    return { lang, dir: meta.dir, locale: meta.locale, setLang, t };
  }, [lang, setLang, t]);

  return React.createElement(LangContext.Provider, { value }, children);
}

export function useLang() {
  return useContext(LangContext);
}

// Locale-aware number formatting (fa-IR renders Persian digits).
export function formatNumber(locale, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat(locale).format(Number(value));
}

// Locale-aware date formatting for ISO strings from the API.
export function formatDate(locale, isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
