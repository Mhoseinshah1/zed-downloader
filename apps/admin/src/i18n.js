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
    "status.denied": "رد شده",

    "common.new": "افزودن",
    "common.edit": "ویرایش",
    "common.delete": "حذف",
    "common.save": "ذخیره",
    "common.saving": "در حال ذخیره…",
    "common.cancel": "انصراف",
    "common.close": "بستن",
    "common.actions": "عملیات",
    "common.all": "همه",
    "common.active": "فعال",
    "common.inactive": "غیرفعال",
    "common.enabled": "فعال",
    "common.disabled": "غیرفعال",
    "common.yes": "بله",
    "common.no": "خیر",
    "common.total": "مجموع: {total}",
    "common.deleteConfirm": "آیا از حذف این مورد مطمئن هستید؟",
    "common.saveFailed": "ذخیره ناموفق بود.",
    "common.filter": "فیلتر",
    "common.status": "وضعیت",
    "common.createdAt": "تاریخ ایجاد",

    "groups.chatId": "شناسه چت",
    "groups.name": "عنوان",
    "groups.username": "نام کاربری",
    "groups.dailyLimit": "محدودیت روزانه",
    "groups.downloadsToday": "دانلود امروز",
    "groups.totalDownloads": "کل دانلودها",
    "groups.editLimit": "ویرایش محدودیت روزانه",
    "groups.limitHint": "برای حذف محدودیت مقدار -1 را وارد کنید.",
    "groups.unlimited": "نامحدود",

    "downloads.user": "کاربر",
    "downloads.url": "لینک",
    "downloads.platform": "پلتفرم",
    "downloads.provider": "سرویس‌دهنده",
    "downloads.fileName": "نام فایل",
    "downloads.fileSize": "حجم",
    "downloads.fileType": "نوع",
    "downloads.error": "خطا",
    "downloads.completedAt": "زمان تکمیل",
    "downloads.allStatuses": "همه وضعیت‌ها",

    "plans.name": "نام",
    "plans.description": "توضیحات",
    "plans.price": "قیمت",
    "plans.currency": "واحد پول",
    "plans.duration": "مدت (روز)",
    "plans.downloadLimit": "محدودیت دانلود",
    "plans.scope": "دامنه",
    "plans.sortOrder": "ترتیب",
    "plans.scopeUser": "کاربر",
    "plans.scopeGroup": "گروه",
    "plans.new": "پلن جدید",
    "plans.edit": "ویرایش پلن",

    "payments.user": "کاربر",
    "payments.plan": "پلن",
    "payments.gateway": "درگاه",
    "payments.amount": "مبلغ",
    "payments.transactionId": "شناسه تراکنش",
    "payments.authority": "کد پیگیری",
    "payments.paidAt": "زمان پرداخت",
    "payStatus.pending": "در انتظار",
    "payStatus.paid": "پرداخت شده",
    "payStatus.completed": "تکمیل شده",
    "payStatus.failed": "ناموفق",
    "payStatus.refunded": "بازگردانده شده",
    "payStatus.cancelled": "لغو شده",
    "payStatus.canceled": "لغو شده",
    "payStatus.expired": "منقضی شده",

    "platforms.name": "نام",
    "platforms.slug": "اسلاگ",
    "platforms.urlRegex": "الگوی URL",
    "platforms.sortOrder": "ترتیب",
    "platforms.new": "پلتفرم جدید",
    "platforms.edit": "ویرایش پلتفرم",

    "providers.name": "نام",
    "providers.slug": "اسلاگ",
    "providers.platform": "پلتفرم",
    "providers.type": "نوع",
    "providers.apiKey": "کلید API",
    "providers.apiKeyHint": "برای حفظ کلید فعلی خالی بگذارید.",
    "providers.hasKey": "کلید تنظیم شده",
    "providers.noKey": "بدون کلید",
    "providers.baseUrl": "آدرس پایه",
    "providers.priority": "اولویت",
    "providers.timeout": "مهلت (ثانیه)",
    "providers.settings": "تنظیمات (JSON)",
    "providers.test": "تست",
    "providers.balance": "موجودی",
    "providers.testOk": "اتصال موفق بود.",
    "providers.testFailed": "تست ناموفق بود.",
    "providers.balanceUnsupported": "موجودی پشتیبانی نمی‌شود.",
    "providers.new": "سرویس‌دهنده جدید",
    "providers.edit": "ویرایش سرویس‌دهنده",
    "providers.invalidJson": "قالب JSON نامعتبر است.",
    "providers.anyPlatform": "بدون پلتفرم",

    "settings.key": "کلید",
    "settings.value": "مقدار",
    "settings.description": "توضیح",

    "ads.adTitle": "عنوان",
    "ads.content": "محتوا",
    "ads.mediaUrl": "لینک رسانه",
    "ads.weight": "وزن",
    "ads.new": "تبلیغ جدید",
    "ads.edit": "ویرایش تبلیغ",

    "fj.channelId": "شناسه کانال",
    "fj.username": "نام کاربری",
    "fj.title": "عنوان",
    "fj.sortOrder": "ترتیب",
    "fj.new": "کانال جدید",
    "fj.edit": "ویرایش کانال",

    "botTexts.key": "کلید",
    "botTexts.lang": "زبان",
    "botTexts.value": "مقدار",
    "botTexts.new": "متن جدید",
    "botTexts.allLangs": "همه زبان‌ها",

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
    "status.denied": "Denied",

    "common.new": "New",
    "common.edit": "Edit",
    "common.delete": "Delete",
    "common.save": "Save",
    "common.saving": "Saving…",
    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.actions": "Actions",
    "common.all": "All",
    "common.active": "Active",
    "common.inactive": "Inactive",
    "common.enabled": "Enabled",
    "common.disabled": "Disabled",
    "common.yes": "Yes",
    "common.no": "No",
    "common.total": "Total: {total}",
    "common.deleteConfirm": "Are you sure you want to delete this item?",
    "common.saveFailed": "Failed to save.",
    "common.filter": "Filter",
    "common.status": "Status",
    "common.createdAt": "Created",

    "groups.chatId": "Chat ID",
    "groups.name": "Title",
    "groups.username": "Username",
    "groups.dailyLimit": "Daily limit",
    "groups.downloadsToday": "Downloads today",
    "groups.totalDownloads": "Total downloads",
    "groups.editLimit": "Edit daily limit",
    "groups.limitHint": "Enter -1 to clear the limit.",
    "groups.unlimited": "Unlimited",

    "downloads.user": "User",
    "downloads.url": "URL",
    "downloads.platform": "Platform",
    "downloads.provider": "Provider",
    "downloads.fileName": "File name",
    "downloads.fileSize": "Size",
    "downloads.fileType": "Type",
    "downloads.error": "Error",
    "downloads.completedAt": "Completed at",
    "downloads.allStatuses": "All statuses",

    "plans.name": "Name",
    "plans.description": "Description",
    "plans.price": "Price",
    "plans.currency": "Currency",
    "plans.duration": "Duration (days)",
    "plans.downloadLimit": "Download limit",
    "plans.scope": "Scope",
    "plans.sortOrder": "Order",
    "plans.scopeUser": "User",
    "plans.scopeGroup": "Group",
    "plans.new": "New plan",
    "plans.edit": "Edit plan",

    "payments.user": "User",
    "payments.plan": "Plan",
    "payments.gateway": "Gateway",
    "payments.amount": "Amount",
    "payments.transactionId": "Transaction ID",
    "payments.authority": "Authority",
    "payments.paidAt": "Paid at",
    "payStatus.pending": "Pending",
    "payStatus.paid": "Paid",
    "payStatus.completed": "Completed",
    "payStatus.failed": "Failed",
    "payStatus.refunded": "Refunded",
    "payStatus.cancelled": "Cancelled",
    "payStatus.canceled": "Cancelled",
    "payStatus.expired": "Expired",

    "platforms.name": "Name",
    "platforms.slug": "Slug",
    "platforms.urlRegex": "URL regex",
    "platforms.sortOrder": "Order",
    "platforms.new": "New platform",
    "platforms.edit": "Edit platform",

    "providers.name": "Name",
    "providers.slug": "Slug",
    "providers.platform": "Platform",
    "providers.type": "Type",
    "providers.apiKey": "API key",
    "providers.apiKeyHint": "Leave blank to keep the current key.",
    "providers.hasKey": "Key set",
    "providers.noKey": "No key",
    "providers.baseUrl": "Base URL",
    "providers.priority": "Priority",
    "providers.timeout": "Timeout (s)",
    "providers.settings": "Settings (JSON)",
    "providers.test": "Test",
    "providers.balance": "Balance",
    "providers.testOk": "Connection OK.",
    "providers.testFailed": "Test failed.",
    "providers.balanceUnsupported": "Balance not supported.",
    "providers.new": "New provider",
    "providers.edit": "Edit provider",
    "providers.invalidJson": "Invalid JSON.",
    "providers.anyPlatform": "No platform",

    "settings.key": "Key",
    "settings.value": "Value",
    "settings.description": "Description",

    "ads.adTitle": "Title",
    "ads.content": "Content",
    "ads.mediaUrl": "Media URL",
    "ads.weight": "Weight",
    "ads.new": "New ad",
    "ads.edit": "Edit ad",

    "fj.channelId": "Channel ID",
    "fj.username": "Username",
    "fj.title": "Title",
    "fj.sortOrder": "Order",
    "fj.new": "New channel",
    "fj.edit": "Edit channel",

    "botTexts.key": "Key",
    "botTexts.lang": "Language",
    "botTexts.value": "Value",
    "botTexts.new": "New text",
    "botTexts.allLangs": "All languages",

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
