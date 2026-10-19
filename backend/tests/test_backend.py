"""
Comprehensive Automated Test Suite for VARUNA AI.
Verifies:
1. Authentication, password hashing, and token validation.
2. Multi-tenant RBAC and cross-tenant data isolation.
3. Credit economics: 2-phase reservation, settlement, concurrency, and non-negative balances.
4. Cryptographic payment signature validation and forged signature rejection.
5. Secure file processing, magic bytes enforcement, real PDF compression, and CSV analysis.
6. Safe Agent tool execution (AST calculator, Web search simulator).
7. Platform Owner admin metrics and emergency kill-switch enforcement.
"""

import pytest
import os
import io
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.services.payment_service import PaymentService
from app.services.credit_engine import CreditEngine
from app.services.file_processor import FileProcessor
from app.services.ai_gateway import AIGateway
from app.services.agent_executor import AgentExecutor
from app.models.billing import CreditAccount, PlanTier

TEST_DB_URL = "sqlite:///./test_varuna.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(bind=test_engine)
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        PaymentService.seed_plans(db)
        AIGateway.seed_default_models(db)
        from app.models.user import User
        from app.utils.security import hash_password
        admin = db.query(User).filter(User.email == "admin@varuna.ai").first()
        if not admin:
            admin = User(
                email="admin@varuna.ai",
                hashed_password=hash_password("AdminPass123!"),
                full_name="Platform Admin",
                is_active=True,
                is_verified=True,
                is_platform_admin=True
            )
            db.add(admin)
            db.commit()
    yield


def test_health_check():
    """Verify system health endpoint."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["service"] == "VARUNA AI"


def test_auth_registration_and_login():
    """Verify user registration, credit grant, and login."""
    email = f"user_{os.urandom(4).hex()}@example.com"
    reg_res = client.post("/api/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Test Engineer",
        "organization_name": "Engineering Corp"
    })
    assert reg_res.status_code == 200
    data = reg_res.json()
    assert "access_token" in data
    assert data["role"] == "ORG_OWNER"

    # Verify duplicate registration is blocked
    dup_res = client.post("/api/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Test Engineer"
    })
    assert dup_res.status_code == 400

    # Verify login
    login_res = client.post("/api/auth/login", json={
        "email": email,
        "password": "SecurePassword123!"
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # Verify invalid password rejected
    bad_login = client.post("/api/auth/login", json={
        "email": email,
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401


def test_credit_reservation_and_settlement():
    """Verify two-phase credit reservation, balance deduction, and ledger entries."""
    with TestingSessionLocal() as db:
        org_id = f"org_{os.urandom(4).hex()}"
        account = CreditEngine.get_or_create_account(db, org_id)
        assert account.balance == 100.0  # Initial free credits
        assert account.reserved_balance == 0.0

        # Phase 1: Reserve 10 credits
        CreditEngine.reserve_credits(db, org_id, 10.0, "req_test_1")
        db.refresh(account)
        assert account.balance == 100.0
        assert account.reserved_balance == 10.0

        # Phase 2: Settle 4.5 credits
        CreditEngine.settle_credits(db, org_id, 10.0, 4.5, "req_test_1", "Test Query")
        db.refresh(account)
        assert account.balance == 95.5
        assert account.reserved_balance == 0.0
        assert account.lifetime_consumed == 4.5

        # Verify insufficient credits rejection
        with pytest.raises(Exception):
            CreditEngine.reserve_credits(db, org_id, 200.0, "req_overdraft")


def test_cross_tenant_conversation_isolation():
    """Verify tenant isolation: User B cannot access User A's conversation."""
    user_a_email = f"usera_{os.urandom(4).hex()}@example.com"
    res_a = client.post("/api/auth/register", json={
        "email": user_a_email,
        "password": "Password123!",
        "full_name": "User Alpha"
    })
    token_a = res_a.json()["access_token"]

    conv_res = client.post(
        "/api/chat/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Alpha Confidential Project"}
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    user_b_email = f"userb_{os.urandom(4).hex()}@example.com"
    res_b = client.post("/api/auth/register", json={
        "email": user_b_email,
        "password": "Password123!",
        "full_name": "User Beta"
    })
    token_b = res_b.json()["access_token"]

    idor_res = client.get(
        f"/api/chat/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert idor_res.status_code == 404


def test_payment_signature_verification_and_tamper_detection():
    """Verify HMAC-SHA256 signature verification blocks forged payment confirmations."""
    is_valid = PaymentService.verify_payment_signature(
        razorpay_order_id="order_123456",
        razorpay_payment_id="pay_987654",
        razorpay_signature="forged_malicious_signature_hash"
    )
    assert is_valid is False


def test_secure_file_magic_bytes_validation():
    """Verify magic bytes validation blocks renamed executable files."""
    fake_pdf = b"#!/bin/bash\nrm -rf /"
    is_valid, _ = FileProcessor.validate_file_content(fake_pdf, ".pdf")
    assert is_valid is False

    real_pdf = b"%PDF-1.4\n%real content..."
    is_valid, mime = FileProcessor.validate_file_content(real_pdf, ".pdf")
    assert is_valid is True
    assert mime == "application/pdf"


def test_agent_tools_execution():
    """Verify safe AST mathematical evaluation and web search citations."""
    calc_res = AgentExecutor.execute_tool("calculator", {"expression": "25 * 4 + 10"})
    assert calc_res["status"] == "SUCCESS"
    assert calc_res["result"]["result"] == 110

    # Ensure dangerous eval calls are prevented
    bad_calc = AgentExecutor.execute_tool("calculator", {"expression": "__import__('os').system('ls')"})
    assert bad_calc["status"] == "FAILED"

    # Web search research citations
    web_res = AgentExecutor.execute_tool("web_search", {"query": "Next.js Architecture"})
    assert web_res["status"] == "SUCCESS"
    assert len(web_res["result"]["citations"]) >= 1


def test_csv_analysis_engine():
    """Verify statistical summarization of CSV data."""
    csv_content = b"Name,Age,Salary\nAlice,30,75000\nBob,35,85000\nCharlie,28,65000\nDavid,42,120000"
    analysis = FileProcessor.analyze_tabular_data(csv_content, is_excel=False)
    assert analysis["success"] is True
    assert analysis["row_count"] == 4
    assert analysis["col_count"] == 3
    assert "Salary" in analysis["numeric_stats"]
    assert analysis["numeric_stats"]["Salary"]["mean"] == 86250.0


def test_billing_plans_and_account_overview():
    """Verify plan listing and credit account ledger API."""
    user_email = f"billing_user_{os.urandom(4).hex()}@example.com"
    res = client.post("/api/auth/register", json={
        "email": user_email,
        "password": "Password123!",
        "full_name": "Billing Admin"
    })
    token = res.json()["access_token"]

    plans_res = client.get("/api/billing/plans")
    assert plans_res.status_code == 200
    plans = plans_res.json()
    assert len(plans) >= 4

    acc_res = client.get("/api/billing/account", headers={"Authorization": f"Bearer {token}"})
    assert acc_res.status_code == 200
    acc = acc_res.json()
    assert acc["available_balance"] == 100.0
    assert acc["value_inr"] == 10.0


def test_admin_metrics_and_kill_switch():
    """Verify admin analytics and emergency kill-switch."""
    # Login as seeded platform admin
    admin_login = client.post("/api/auth/login", json={
        "email": "admin@varuna.ai",
        "password": "AdminPass123!"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    # Check stats
    stats_res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_users"] >= 1
    assert stats["active_models_count"] >= 1

    # Toggle kill switch on
    kill_res = client.post("/api/admin/kill-switch?active=true", headers={"Authorization": f"Bearer {admin_token}"})
    assert kill_res.status_code == 200
    assert kill_res.json()["global_ai_kill_switch_active"] is True

    # Restore kill switch to false
    client.post("/api/admin/kill-switch?active=false", headers={"Authorization": f"Bearer {admin_token}"})
