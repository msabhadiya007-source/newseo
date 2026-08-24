"""Auth & RBAC tests: /api/auth/login, /me, /register, permission gating."""
import uuid

import requests
from conftest import API


class TestAuth:
    def test_login_success(self, anon, test_credentials):
        r = anon.post(f"{API}/auth/login", json=test_credentials)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("token"), str) and len(data["token"]) > 20
        assert data["user"]["email"] == test_credentials["email"].lower()
        assert data["user"]["role"] == "admin"
        assert "password_hash" not in data["user"]
        assert "_id" not in data["user"]

    def test_login_invalid_password(self, anon, test_credentials):
        r = anon.post(f"{API}/auth/login",
                      json={"email": test_credentials["email"], "password": "WrongPass!123"})
        assert r.status_code == 401, r.text

    def test_me_with_bearer(self, client, test_credentials):
        r = client.get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["email"] == test_credentials["email"].lower()
        assert "publish" in data["permissions"]

    def test_me_without_token(self, anon):
        r = anon.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token(self, anon):
        r = anon.get(f"{API}/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_bcrypt_hash_format(self):
        """Password hashes must be bcrypt $2b$."""
        import sys
        sys.path.insert(0, "/app/backend")
        from auth import hash_password, verify_password
        h = hash_password("Sample@123")
        assert h.startswith("$2b$"), h[:10]
        assert verify_password("Sample@123", h)
        assert not verify_password("bad", h)


class TestRBAC:
    """Register a viewer + seo_editor and verify permission gating."""

    created = []

    def _register(self, client, role):
        email = f"test_{role}_{uuid.uuid4().hex[:6]}@example.com"
        pwd = "TestPass@2026"
        r = client.post(f"{API}/auth/register",
                        json={"email": email, "password": pwd, "name": f"TEST {role}", "role": role})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == role
        self.created.append(email)
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}).json()["token"]
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
        return s

    def test_register_requires_admin(self, anon):
        r = anon.post(f"{API}/auth/register",
                      json={"email": "nope@example.com", "password": "x", "name": "x", "role": "viewer"})
        assert r.status_code == 401

    def test_register_invalid_role(self, client):
        r = client.post(f"{API}/auth/register", json={
            "email": f"test_bad_{uuid.uuid4().hex[:6]}@example.com",
            "password": "TestPass@2026", "name": "TEST", "role": "superuser"})
        assert r.status_code == 400, r.text

    def test_viewer_cannot_publish_or_sync_or_edit(self, client):
        viewer = self._register(client, "viewer")
        pid = client.get(f"{API}/products?page_size=1").json()["items"][0]["id"]

        r = viewer.get(f"{API}/products?page_size=1")
        assert r.status_code == 200, "viewer must be able to read"

        r = viewer.post(f"{API}/products/{pid}/publish-seo", json={"seo_title": "x"})
        assert r.status_code == 403, r.text
        r = viewer.patch(f"{API}/products/{pid}/seo-draft", json={"seo_title": "x"})
        assert r.status_code == 403, r.text
        r = viewer.post(f"{API}/sync", json={})
        assert r.status_code == 403, r.text
        r = viewer.post(f"{API}/products/{pid}/rollback", json={})
        assert r.status_code == 403, r.text
        r = viewer.get(f"{API}/auth/users")
        assert r.status_code == 403, r.text

    def test_seo_editor_cannot_sync_or_rollback_or_settings(self, client):
        editor = self._register(client, "seo_editor")
        r = editor.post(f"{API}/sync", json={})
        assert r.status_code == 403, r.text
        r = editor.put(f"{API}/settings", json={"title_max": 60})
        assert r.status_code == 403, r.text

    def test_brute_force_lockout(self, anon):
        """>5 wrong passwords for a fresh account -> 429 lockout.

        KNOWN BUG: the lockout key is f"{request.client.host}:{email}". Behind the k8s
        ingress request.client.host is the proxy pod IP, which rotates across replicas, so
        attempts are split across several counters and the lockout may never fire. Backend
        must use the X-Forwarded-For client IP (or key on email alone).
        """
        email = f"test_lock_{uuid.uuid4().hex[:6]}@example.com"
        codes = []
        for _ in range(20):
            r = anon.post(f"{API}/auth/login", json={"email": email, "password": "wrong"})
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"No lockout after {len(codes)} failed attempts, codes={codes}"
