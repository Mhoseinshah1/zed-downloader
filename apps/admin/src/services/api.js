import axios from "axios";

// Token storage keys (canonical — used by auth.js and route guards too).
export const ACCESS_TOKEN_KEY = "zed_access_token";
export const REFRESH_TOKEN_KEY = "zed_refresh_token";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(data) {
  if (data && data.access_token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
  }
  if (data && data.refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  }
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

// Attach Bearer token to every request when available.
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Shared in-flight refresh promise so concurrent 401s trigger a single refresh call.
let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error("no_refresh_token");
  }
  // Use a bare axios call to bypass this instance's interceptors.
  const res = await axios.post("/api/admin/auth/refresh", {
    refresh_token: refreshToken,
  });
  setTokens(res.data);
  return res.data.access_token;
}

function isAuthPath(url) {
  return (
    typeof url === "string" &&
    (url.includes("/admin/auth/login") || url.includes("/admin/auth/refresh"))
  );
}

// On 401: try refresh ONCE, then retry the original request.
// On refresh failure: clear tokens and redirect to /login.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response ? error.response.status : null;

    if (status === 401 && original && !original._retried && !isAuthPath(original.url)) {
      original._retried = true;
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null;
          });
        }
        const newToken = await refreshPromise;
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch (refreshError) {
        clearTokens();
        if (window.location.pathname !== "/login") {
          window.location.assign("/login");
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
