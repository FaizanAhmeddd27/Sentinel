import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
class TestAuthEndpoints:

    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should always return 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sentinel-backend"

    async def test_root_endpoint(self, client: AsyncClient):
        """Root endpoint returns service info."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Sentinel" in data["service"]
        assert "docs" in data

    async def test_google_login_redirect(self, client: AsyncClient):
        """
        /auth/google/login should redirect to Google.
        We mock OAuth to avoid real Google call.
        """
        with patch(
            "app.api.auth.oauth.google.authorize_redirect",
            new_callable=AsyncMock,
            return_value=MagicMock(status_code=302),
        ):
            response = await client.get(
                "/auth/google/login",
                follow_redirects=False,
            )
            # Should attempt redirect (302) or return redirect response
            assert response.status_code in [200, 302, 303]

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        """GET /auth/me without token should return 401."""
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_logout_unauthenticated(self, client: AsyncClient):
        """POST /auth/logout without token should return 401."""
        response = await client.post("/auth/logout")
        assert response.status_code == 401

    async def test_refresh_without_cookie(self, client: AsyncClient):
        """POST /auth/refresh without refresh cookie should return 401."""
        response = await client.post("/auth/refresh")
        assert response.status_code == 401

    async def test_system_status(self, client: AsyncClient):
        """GET /system/status should return module status."""
        response = await client.get("/system/status")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert data["modules"]["correlation_engine"] is True
        assert data["modules"]["reconciliation_assistant"] is True
        assert data["modules"]["ai_incident_summary"] is True

    async def test_protected_route_no_token(self, client: AsyncClient):
        """Any protected route without JWT should return 401."""
        protected_routes = [
            ("GET", "/incidents"),
            ("GET", "/users"),
            ("GET", "/ingestion/jobs"),
            ("GET", "/playbooks"),
            ("GET", "/quarantine"),
            ("GET", "/analytics/roi"),
        ]
        for method, path in protected_routes:
            if method == "GET":
                response = await client.get(path)
            else:
                response = await client.post(path)
            assert response.status_code == 401, (
                f"Expected 401 for {method} {path}, got {response.status_code}"
            )

    async def test_jwt_token_invalid(self, client: AsyncClient):
        """Malformed JWT should return 401."""
        headers = {"Authorization": "Bearer this.is.not.a.valid.jwt"}
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 401

    async def test_jwt_token_expired(self, client: AsyncClient):
        """Expired JWT should return 401."""
        # This is a real JWT structure but signed with wrong key / expired
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwiZXhwIjoxfQ."
            "invalid_signature"
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 401