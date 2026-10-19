"""
Phase 1 Verification Test Suite for VARUNA AI.
Validates:
1. Environment configuration loading and settings schema.
2. Application initialization and dependency compatibility.
3. Health check endpoints (/health and /api/health).
4. Request correlation ID injection (X-Request-ID).
5. CORS configuration.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_environment_configuration_schema():
    """Verify that settings are loaded with correct types and defaults."""
    assert settings.APP_NAME == "VARUNA AI"
    assert settings.APP_VERSION == "1.0.0"
    assert isinstance(settings.PORT, int)
    assert settings.PORT == 8000
    assert len(settings.SECRET_KEY) >= 32
    assert "http://localhost:3000" in settings.ALLOWED_ORIGINS
    assert settings.CREDIT_VALUE_INR == 0.10
    assert settings.SIGNUP_FREE_CREDITS == 100.0


def test_root_health_check():
    """Verify /health endpoint returns HTTP 200 with healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["service"] == "VARUNA AI"
    assert data["version"] == "1.0.0"
    assert "environment" in data


def test_api_health_check_probe():
    """Verify /api/health endpoint behaves identically for load balancers."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"


def test_request_correlation_id_middleware():
    """Verify X-Request-ID is generated and returned on all requests."""
    # Without incoming header
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert "X-Request-ID" in res1.headers
    generated_id = res1.headers["X-Request-ID"]
    assert len(generated_id) > 10

    # With client-provided header
    custom_id = "test-custom-request-id-12345"
    res2 = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res2.status_code == 200
    assert res2.headers["X-Request-ID"] == custom_id
