/**
 * Shopify embedded-app helpers (App Bridge + Token Exchange kickoff).
 *
 * The app is embedded inside Shopify Admin. We load Shopify App Bridge from the
 * official CDN, obtain a fresh session (ID) token, and send it to the backend
 * token-exchange endpoint. The Admin API access token is NEVER handled here — it
 * is obtained and stored entirely server-side.
 */
import { API } from "@/lib/api";

let _bridgeReady = null;

/** Public, non-secret config (client id / api key) served by the backend. */
export async function getShopifyConfig() {
  const res = await fetch(`${API}/shopify/config`);
  if (!res.ok) throw new Error("Failed to load Shopify config.");
  return res.json(); // { api_key, app_configured, shop }
}

/** True when running inside an iframe (Shopify Admin embeds the app). */
export function isEmbedded() {
  try {
    return window.top !== window.self;
  } catch {
    return true;
  }
}

/**
 * Load Shopify App Bridge exactly once, injecting the required api-key meta tag
 * BEFORE the script executes. Resolves with the global `window.shopify`.
 */
export async function ensureAppBridge() {
  if (window.shopify && typeof window.shopify.idToken === "function") return window.shopify;

  // App Bridge only works when the app is embedded inside Shopify Admin. Loading the
  // CDN script in a standalone browser tab makes App Bridge abort with a thrown error
  // ("must be the first <script> tag ... Aborting"), so we never load it here. This
  // check lives OUTSIDE the cached promise so it always fails fast (and cleanly).
  if (!isEmbedded()) {
    throw new Error("NOT_EMBEDDED");
  }

  if (_bridgeReady) return _bridgeReady;

  _bridgeReady = (async () => {
    const cfg = await getShopifyConfig();
    if (!cfg.api_key) {
      throw new Error("Shopify app is not configured on the server (missing SHOPIFY_CLIENT_ID).");
    }
    if (!document.querySelector('meta[name="shopify-api-key"]')) {
      const meta = document.createElement("meta");
      meta.name = "shopify-api-key";
      meta.content = cfg.api_key;
      document.head.prepend(meta);
    }
    await new Promise((resolve, reject) => {
      if (document.getElementById("shopify-app-bridge-cdn")) {
        resolve();
        return;
      }
      const s = document.createElement("script");
      s.id = "shopify-app-bridge-cdn";
      s.async = false; // App Bridge must NOT be async/defer/module
      s.src = "https://cdn.shopify.com/shopifycloud/app-bridge.js";
      s.onload = resolve;
      s.onerror = () => reject(new Error("Failed to load Shopify App Bridge script."));
      document.head.appendChild(s);
    });
    // Wait (up to ~5s) for the global to initialise.
    for (let i = 0; i < 50; i++) {
      if (window.shopify && typeof window.shopify.idToken === "function") return window.shopify;
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("Shopify App Bridge did not initialise. Open the app inside Shopify Admin.");
  })().catch((e) => {
    // Do not cache failures so a later (embedded) attempt can retry cleanly.
    _bridgeReady = null;
    throw e;
  });

  return _bridgeReady;
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
