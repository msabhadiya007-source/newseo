/**
 * Shopify embedded-app helpers (App Bridge + Token Exchange kickoff).
 *
 * The app is embedded inside Shopify Admin. We load Shopify App Bridge from the
 * official CDN, obtain a fresh session (ID) token, and send it to the backend
 * token-exchange endpoint. The Admin API access token is NEVER handled here — it
 * is obtained and stored entirely server-side.
 */
import { API } from "@/lib/api";

/** Public, non-secret config (client id / api key) served by the backend. */
export async function getShopifyConfig() {
  const res = await fetch(`${API}/shopify/config`);
  if (!res.ok) throw new Error("Failed to load Shopify config.");
  return res.json(); // { api_key, app_configured, shop }
}

/** True when running inside Shopify Admin (embedded iframe or a host/embedded param). */
export function isEmbedded() {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.has("host") || params.get("embedded") === "1") return true;
    return window.top !== window.self;
  } catch {
    // Cross-origin access to window.top throws only inside an iframe -> embedded.
    return true;
  }
}

/**
 * Resolve the global `window.shopify` provided by App Bridge.
 *
 * App Bridge v4 is loaded statically from Shopify's CDN in the initial <head>
 * (see public/index.html) with the shopify-api-key meta injected at build time from
 * REACT_APP_SHOPIFY_API_KEY. Here we only WAIT for the global to be ready.
 *
 * IMPORTANT: the embedded check runs FIRST. App Bridge's script is present on every
 * page (even a standalone tab), so `window.shopify` may exist outside Shopify Admin —
 * but calling idToken() there never resolves. Failing fast keeps standalone graceful.
 */
export async function ensureAppBridge() {
  if (!isEmbedded()) {
    throw new Error("NOT_EMBEDDED");
  }
  if (window.shopify && typeof window.shopify.idToken === "function") return window.shopify;
  // App Bridge is loaded from index.html; give it a moment to initialise (race-safe).
  for (let i = 0; i < 100; i++) { // up to ~10s
    if (window.shopify && typeof window.shopify.idToken === "function") return window.shopify;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("Shopify App Bridge did not initialise. Open the app inside Shopify Admin.");
}

/** Obtain a fresh, short-lived Shopify session (ID) token via App Bridge. */
export async function getSessionToken() {
  const bridge = await ensureAppBridge();
  return bridge.idToken();
}

/**
 * Full authentication: fetch a fresh ID token and exchange it server-side.
 * The backend validates it and stores an OFFLINE Admin token encrypted at rest.
 * Returns non-secret status { authenticated, shop, granted_scopes, message }.
 */
export async function authenticateWithShopify() {
  const idToken = await getSessionToken();
  const res = await fetch(`${API}/shopify/auth/token-exchange`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const msg = (detail && typeof detail === "object" ? detail.message : detail) || "Shopify authentication failed.";
    throw new Error(typeof msg === "string" ? msg : "Shopify authentication failed.");
  }
  return data;
}
