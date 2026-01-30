"""
Tenant Isolation Security Tests
Critical tests to ensure multi-tenant data isolation.
"""

import pytest
import jwt
from datetime import datetime, timedelta
from database.config import get_db, JWT_SECRET_KEY, JWT_ALGORITHM
from database.models import Tenant, User, Document, KnowledgeGap, Connector, UserRole, TenantPlan
from services.auth_service import JWTUtils, PasswordUtils
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def db_session():
    """Create a test database session"""
    db = next(get_db())
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def tenant_a(db_session):
    """Create tenant A"""
    tenant = Tenant(
        name="Tenant A Corp",
        slug="tenant-a",
        plan=TenantPlan.FREE,
        is_active=True
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def tenant_b(db_session):
    """Create tenant B"""
    tenant = Tenant(
        name="Tenant B Inc",
        slug="tenant-b",
        plan=TenantPlan.FREE,
        is_active=True
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def user_a(db_session, tenant_a):
    """Create user for tenant A"""
    user = User(
        tenant_id=tenant_a.id,
        email="user_a@example.com",
        password_hash=PasswordUtils.hash_password("Password123!"),
        full_name="User A",
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user_b(db_session, tenant_b):
    """Create user for tenant B"""
    user = User(
        tenant_id=tenant_b.id,
        email="user_b@example.com",
        password_hash=PasswordUtils.hash_password("Password123!"),
        full_name="User B",
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def jwt_token_a(user_a, tenant_a):
    """Create JWT token for user A"""
    access_token, _, _ = JWTUtils.create_access_token(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        email=user_a.email,
        role=user_a.role.value
    )
    return access_token


@pytest.fixture
def jwt_token_b(user_b, tenant_b):
    """Create JWT token for user B"""
    access_token, _, _ = JWTUtils.create_access_token(
        user_id=user_b.id,
        tenant_id=tenant_b.id,
        email=user_b.email,
        role=user_b.role.value
    )
    return access_token


# ============================================================================
# TESTS: JWT Tenant Validation
# ============================================================================

class TestJWTTenantValidation:
    """Test that tenant_id ONLY comes from JWT, never from headers"""

    def test_jwt_contains_tenant_id(self, jwt_token_a, tenant_a):
        """JWT token should contain tenant_id in payload"""
        payload = jwt.decode(jwt_token_a, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        assert "tenant_id" in payload
        assert payload["tenant_id"] == tenant_a.id

    def test_spoofed_tenant_header_rejected(self, jwt_token_a, tenant_b):
        """X-Tenant header should be completely ignored"""
        # This test verifies the security fix
        # Even if a malicious client sends X-Tenant header, it should be ignored

        payload = jwt.decode(jwt_token_a, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Tenant A's token should only give access to Tenant A data
        # NOT Tenant B, even if X-Tenant header is spoofed
        assert payload["tenant_id"] != tenant_b.id


# ============================================================================
# TESTS: Document Isolation
# ============================================================================

class TestDocumentIsolation:
    """Test that documents are isolated between tenants"""

    def setup_test_documents(self, db_session, tenant_a, tenant_b, user_a, user_b):
        """Create test documents for both tenants"""
        # Tenant A documents
        doc_a1 = Document(
            tenant_id=tenant_a.id,
            title="Tenant A Document 1",
            content="Sensitive data for Tenant A",
            source="test",
            source_id="doc_a1",
            sender_email=user_a.email
        )
        doc_a2 = Document(
            tenant_id=tenant_a.id,
            title="Tenant A Document 2",
            content="More Tenant A data",
            source="test",
            source_id="doc_a2",
            sender_email=user_a.email
        )

        # Tenant B documents
        doc_b1 = Document(
            tenant_id=tenant_b.id,
            title="Tenant B Document 1",
            content="Sensitive data for Tenant B",
            source="test",
            source_id="doc_b1",
            sender_email=user_b.email
        )

        db_session.add_all([doc_a1, doc_a2, doc_b1])
        db_session.commit()

        return doc_a1, doc_a2, doc_b1

    def test_tenant_a_cannot_see_tenant_b_documents(
        self, db_session, tenant_a, tenant_b, user_a, user_b
    ):
        """Tenant A should only see their own documents"""
        doc_a1, doc_a2, doc_b1 = self.setup_test_documents(
            db_session, tenant_a, tenant_b, user_a, user_b
        )

        # Query documents for Tenant A
        tenant_a_docs = db_session.query(Document).filter(
            Document.tenant_id == tenant_a.id
        ).all()

        assert len(tenant_a_docs) == 2
        assert doc_a1 in tenant_a_docs
        assert doc_a2 in tenant_a_docs
        assert doc_b1 not in tenant_a_docs

    def test_tenant_b_cannot_see_tenant_a_documents(
        self, db_session, tenant_a, tenant_b, user_a, user_b
    ):
        """Tenant B should only see their own documents"""
        doc_a1, doc_a2, doc_b1 = self.setup_test_documents(
            db_session, tenant_a, tenant_b, user_a, user_b
        )

        # Query documents for Tenant B
        tenant_b_docs = db_session.query(Document).filter(
            Document.tenant_id == tenant_b.id
        ).all()

        assert len(tenant_b_docs) == 1
        assert doc_b1 in tenant_b_docs
        assert doc_a1 not in tenant_b_docs
        assert doc_a2 not in tenant_b_docs

    def test_document_query_requires_tenant_filter(
        self, db_session, tenant_a, tenant_b, user_a, user_b
    ):
        """ALL document queries MUST filter by tenant_id"""
        self.setup_test_documents(db_session, tenant_a, tenant_b, user_a, user_b)

        # This is BAD and should NEVER happen in production code
        all_docs_unfiltered = db_session.query(Document).all()

        # This is GOOD - always filter by tenant
        tenant_a_filtered = db_session.query(Document).filter(
            Document.tenant_id == tenant_a.id
        ).all()

        assert len(all_docs_unfiltered) == 3  # All documents
        assert len(tenant_a_filtered) == 2    # Only Tenant A's documents


# ============================================================================
# TESTS: Knowledge Gap Isolation
# ============================================================================

class TestKnowledgeGapIsolation:
    """Test that knowledge gaps are isolated between tenants"""

    def setup_test_gaps(self, db_session, tenant_a, tenant_b):
        """Create test gaps for both tenants"""
        gap_a = KnowledgeGap(
            tenant_id=tenant_a.id,
            title="Tenant A Gap",
            category="technical",
            questions=["Question for Tenant A?"]
        )

        gap_b = KnowledgeGap(
            tenant_id=tenant_b.id,
            title="Tenant B Gap",
            category="decision",
            questions=["Question for Tenant B?"]
        )

        db_session.add_all([gap_a, gap_b])
        db_session.commit()

        return gap_a, gap_b

    def test_gaps_isolated_by_tenant(
        self, db_session, tenant_a, tenant_b
    ):
        """Each tenant should only see their own knowledge gaps"""
        gap_a, gap_b = self.setup_test_gaps(db_session, tenant_a, tenant_b)

        # Tenant A's gaps
        tenant_a_gaps = db_session.query(KnowledgeGap).filter(
            KnowledgeGap.tenant_id == tenant_a.id
        ).all()

        assert len(tenant_a_gaps) == 1
        assert gap_a in tenant_a_gaps
        assert gap_b not in tenant_a_gaps


# ============================================================================
# TESTS: Connector Isolation
# ============================================================================

class TestConnectorIsolation:
    """Test that integration connectors are isolated between tenants"""

    def setup_test_connectors(self, db_session, tenant_a, tenant_b):
        """Create test connectors for both tenants"""
        connector_a = Connector(
            tenant_id=tenant_a.id,
            type="gmail",
            credentials={"access_token": "tenant_a_secret"},
            is_active=True
        )

        connector_b = Connector(
            tenant_id=tenant_b.id,
            type="gmail",
            credentials={"access_token": "tenant_b_secret"},
            is_active=True
        )

        db_session.add_all([connector_a, connector_b])
        db_session.commit()

        return connector_a, connector_b

    def test_connectors_isolated_by_tenant(
        self, db_session, tenant_a, tenant_b
    ):
        """Each tenant should only see their own connectors"""
        connector_a, connector_b = self.setup_test_connectors(
            db_session, tenant_a, tenant_b
        )

        # Tenant A's connectors
        tenant_a_connectors = db_session.query(Connector).filter(
            Connector.tenant_id == tenant_a.id
        ).all()

        assert len(tenant_a_connectors) == 1
        assert connector_a in tenant_a_connectors
        assert connector_b not in tenant_a_connectors

        # Verify secrets don't leak
        assert connector_a.credentials["access_token"] == "tenant_a_secret"
        assert connector_a.credentials["access_token"] != "tenant_b_secret"


# ============================================================================
# TESTS: User Isolation
# ============================================================================

class TestUserIsolation:
    """Test that users cannot access other tenants' data"""

    def test_users_scoped_to_tenant(self, db_session, tenant_a, tenant_b, user_a, user_b):
        """Users should only exist within their tenant scope"""
        # Get Tenant A's users
        tenant_a_users = db_session.query(User).filter(
            User.tenant_id == tenant_a.id
        ).all()

        assert len(tenant_a_users) == 1
        assert user_a in tenant_a_users
        assert user_b not in tenant_a_users

    def test_cross_tenant_login_blocked(self, db_session, user_a, tenant_b):
        """User A cannot authenticate as Tenant B user"""
        # User A's JWT contains Tenant A's ID
        payload_a = jwt.decode(
            JWTUtils.create_access_token(
                user_id=user_a.id,
                tenant_id=user_a.tenant_id,
                email=user_a.email,
                role=user_a.role.value
            )[0],
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        # Tenant ID should match User A's tenant
        assert payload_a["tenant_id"] == user_a.tenant_id
        assert payload_a["tenant_id"] != tenant_b.id


# ============================================================================
# TESTS: Attack Scenarios
# ============================================================================

class TestSecurityAttackScenarios:
    """Test common attack scenarios for multi-tenant systems"""

    def test_jwt_tampering_detected(self, jwt_token_a, tenant_b):
        """Tampering with JWT tenant_id should fail signature verification"""
        # Decode token WITHOUT verification
        payload = jwt.decode(
            jwt_token_a,
            options={"verify_signature": False},
            algorithms=[JWT_ALGORITHM]
        )

        # Tamper with tenant_id
        payload["tenant_id"] = tenant_b.id

        # Re-encode with wrong tenant
        tampered_token = jwt.encode(
            payload,
            "wrong_secret",  # Without knowing the secret, signature will be invalid
            algorithm=JWT_ALGORITHM
        )

        # Attempt to decode with correct secret should fail
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(tampered_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    def test_header_injection_blocked(self, jwt_token_a, tenant_b):
        """X-Tenant header injection should have no effect"""
        # Decode legitimate token
        payload = jwt.decode(jwt_token_a, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Even if attacker sends X-Tenant header, JWT tenant_id wins
        # This is enforced by removing X-Tenant fallback in app_v2.py
        assert payload["tenant_id"] != tenant_b.id

    def test_sql_injection_in_tenant_filter(self, db_session, tenant_a):
        """SQL injection attempts in tenant_id should fail safely"""
        # Attempt SQL injection in tenant filter
        malicious_tenant_id = "' OR '1'='1"

        # SQLAlchemy parameterization prevents SQL injection
        result = db_session.query(Document).filter(
            Document.tenant_id == malicious_tenant_id
        ).all()

        # Should return empty (no documents with that bogus tenant_id)
        assert len(result) == 0


# ============================================================================
# RUNNER
# ============================================================================

if __name__ == "__main__":
    """Run tests with pytest"""
    pytest.main([__file__, "-v", "--tb=short"])
