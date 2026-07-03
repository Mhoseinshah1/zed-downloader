import api, { setTokens, clearTokens, getAccessToken } from "./api";

const ADMIN_KEY = "zed_admin";

export async function login(email, password) {
  const { data } = await api.post("/admin/auth/login", { email, password });
  setTokens(data);
  if (data.admin) {
    localStorage.setItem(ADMIN_KEY, JSON.stringify(data.admin));
  }
  return data.admin || null;
}

export async function logout() {
  try {
    await api.post("/admin/auth/logout");
  } catch {
    // Best effort — clear the local session regardless of server response.
  }
  clearTokens();
  localStorage.removeItem(ADMIN_KEY);
}

export async function me() {
  const { data } = await api.get("/admin/me");
  localStorage.setItem(ADMIN_KEY, JSON.stringify(data));
  return data;
}

export function getStoredAdmin() {
  try {
    const raw = localStorage.getItem(ADMIN_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isAuthenticated() {
  return Boolean(getAccessToken());
}
