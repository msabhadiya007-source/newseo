"""Ad-hoc preview check for the Shopify Token Exchange endpoint.

Crafts session (ID) tokens signed with the *preview test* client secret and hits the
running backend to verify JWT validation branches. Real Shopify exchange cannot succeed
in preview (no real store), so a validated token is expected to reach the exchange step
and fail there with a 502 (that's the success signal for validation).
"""
import time
import jwt
import requests

BASE = "http://localhost:8001"
SECRET = "preview_test_client_secret_do_not_use_in_prod"
CLIENT_ID = "preview_test_client_id"
SHOP = "preview-demo-shop.myshopify.com"


def make_token(**overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://{SHOP}/admin",
        "dest": f"https://{SHOP}",
        "aud": CLIENT_ID,
        "sub": "user-123",
        "exp": now + 60,
        "nbf": now - 5,
        "iat": now - 5,
        "jti": "jti-abc",
        "sid": "sid-xyz",
    }
    claims.update(overrides)
    secret = overrides.pop("_secret", SECRET)
    return jwt.encode(claims, secret, algorithm="HS256")


def post(token):
    r = requests.post(f"{BASE}/api/shopify/auth/token-exchange",
                      headers={"Authorization": f"Bearer {token}"}, timeout=35)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def code_of(body):
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, dict):
            return d.get("code")
    return None


def main():
    print("public config:", requests.get(f"{BASE}/api/shopify/config").json())

    # 1) valid token -> validation passes, exchange step reached (502 expected in preview)
    sc, body = post(make_token())
    print("\n[valid token] status=", sc, "code=", code_of(body), "body=", body)
    assert sc == 502 and code_of(body) in ("EXCHANGE_FAILED", "EXCHANGE_UNAVAILABLE", "EXCHANGE_NO_TOKEN"), \
        "validation should pass and reach exchange"

    # 2) bad signature
    sc, body = post(make_token(_secret="wrong_secret"))
    print("[bad sig] status=", sc, "code=", code_of(body))
    assert sc == 401 and code_of(body) == "INVALID_ID_TOKEN"

    # 3) expired
    sc, body = post(make_token(exp=int(time.time()) - 100, nbf=int(time.time()) - 200))
    print("[expired] status=", sc, "code=", code_of(body))
    assert sc == 401 and code_of(body) == "TOKEN_EXPIRED"

    # 4) wrong audience
    sc, body = post(make_token(aud="some_other_app"))
    print("[bad aud] status=", sc, "code=", code_of(body))
    assert sc == 401 and code_of(body) == "INVALID_AUDIENCE"

    # 5) iss/dest shop mismatch
    sc, body = post(make_token(iss="https://evil-shop.myshopify.com/admin"))
    print("[shop mismatch] status=", sc, "code=", code_of(body))
    assert sc == 401 and code_of(body) == "SHOP_MISMATCH"

    # 6) non-myshopify shop
    sc, body = post(make_token(iss="https://evil.example.com/admin", dest="https://evil.example.com"))
    print("[bad shop host] status=", sc, "code=", code_of(body))
    assert sc == 401 and code_of(body) == "INVALID_SHOP"

    # 7) missing bearer
    r = requests.post(f"{BASE}/api/shopify/auth/token-exchange", timeout=10)
    print("[no bearer] status=", r.status_code)
    assert r.status_code == 401

    print("\nALL VALIDATION BRANCHES PASSED ✅")


if __name__ == "__main__":
    main()
