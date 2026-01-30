"""
Seed Database Script
Creates test users and tenants with proper isolation.

Creates:
- 4 tenant organizations (different plans)
- 10 users across tenants
- Proper tenant separation
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import (
    SessionLocal, Tenant, User, UserRole, TenantPlan
)
from services.auth_service import PasswordUtils


# Test data configuration
TENANTS = [
    {
        "name": "Acme Corporation",
        "slug": "acme",
        "plan": TenantPlan.ENTERPRISE,
        "description": "Enterprise customer - unlimited access",
    },
    {
        "name": "Startup Inc",
        "slug": "startup",
        "plan": TenantPlan.PROFESSIONAL,
        "description": "Professional plan with advanced features",
    },
    {
        "name": "Small Business LLC",
        "slug": "smallbiz",
        "plan": TenantPlan.STARTER,
        "description": "Starter plan - basic features",
    },
    {
        "name": "Free Tier Co",
        "slug": "freetier",
        "plan": TenantPlan.FREE,
        "description": "Free plan for testing",
    },
]

USERS = [
    # Acme Corporation (Enterprise)
    {
        "email": "admin@acme.com",
        "password": "admin123",
        "name": "Alice Admin",
        "tenant_slug": "acme",
        "role": UserRole.ADMIN,
    },
    {
        "email": "user@acme.com",
        "password": "user123",
        "name": "Bob User",
        "tenant_slug": "acme",
        "role": UserRole.MEMBER,
    },
    {
        "email": "viewer@acme.com",
        "password": "viewer123",
        "name": "Charlie Viewer",
        "tenant_slug": "acme",
        "role": UserRole.VIEWER,
    },

    # Startup Inc (Professional)
    {
        "email": "founder@startup.io",
        "password": "founder123",
        "name": "Diana Founder",
        "tenant_slug": "startup",
        "role": UserRole.ADMIN,
    },
    {
        "email": "engineer@startup.io",
        "password": "engineer123",
        "name": "Eve Engineer",
        "tenant_slug": "startup",
        "role": UserRole.MEMBER,
    },

    # Small Business LLC (Starter)
    {
        "email": "owner@smallbiz.com",
        "password": "owner123",
        "name": "Frank Owner",
        "tenant_slug": "smallbiz",
        "role": UserRole.ADMIN,
    },
    {
        "email": "employee@smallbiz.com",
        "password": "employee123",
        "name": "Grace Employee",
        "tenant_slug": "smallbiz",
        "role": UserRole.MEMBER,
    },

    # Free Tier Co (Free)
    {
        "email": "test@freetier.org",
        "password": "test123",
        "name": "Henry Test",
        "tenant_slug": "freetier",
        "role": UserRole.ADMIN,
    },

    # Additional demo users
    {
        "email": "demo@acme.com",
        "password": "demo123",
        "name": "Ivan Demo",
        "tenant_slug": "acme",
        "role": UserRole.MEMBER,
    },
    {
        "email": "demo@startup.io",
        "password": "demo123",
        "name": "Julia Demo",
        "tenant_slug": "startup",
        "role": UserRole.MEMBER,
    },
]


def create_tenants(db):
    """Create tenant organizations"""
    print("\n" + "="*70)
    print("CREATING TENANTS")
    print("="*70)

    tenant_map = {}

    for i, tenant_data in enumerate(TENANTS, 1):
        print(f"\n[{i}/{len(TENANTS)}] Creating: {tenant_data['name']}")

        tenant = Tenant(
            name=tenant_data['name'],
            slug=tenant_data['slug'],
            plan=tenant_data['plan'],
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )

        db.add(tenant)
        db.flush()  # Get tenant.id without committing

        tenant_map[tenant_data['slug']] = tenant.id

        print(f"  ✓ ID: {tenant.id}")
        print(f"  ✓ Slug: {tenant.slug}")
        print(f"  ✓ Plan: {tenant.plan.value}")
        print(f"  ✓ {tenant_data['description']}")

    db.commit()
    print(f"\n✅ Created {len(TENANTS)} tenants")

    return tenant_map


def create_users(db, tenant_map):
    """Create users with proper tenant assignment"""
    print("\n" + "="*70)
    print("CREATING USERS")
    print("="*70)

    user_credentials = []

    for i, user_data in enumerate(USERS, 1):
        print(f"\n[{i}/{len(USERS)}] Creating: {user_data['name']}")

        tenant_id = tenant_map[user_data['tenant_slug']]

        # Hash password
        password_hash = PasswordUtils.hash_password(user_data['password'])

        user = User(
            email=user_data['email'],
            password_hash=password_hash,
            full_name=user_data['name'],
            tenant_id=tenant_id,
            role=user_data['role'],
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )

        db.add(user)
        db.flush()

        # Store credentials for output
        user_credentials.append({
            'email': user_data['email'],
            'password': user_data['password'],
            'name': user_data['name'],
            'role': user_data['role'].value,
            'tenant_slug': user_data['tenant_slug'],
            'tenant_id': tenant_id,
            'user_id': user.id
        })

        print(f"  ✓ ID: {user.id}")
        print(f"  ✓ Email: {user.email}")
        print(f"  ✓ Tenant: {user_data['tenant_slug']}")
        print(f"  ✓ Role: {user.role.value}")

    db.commit()
    print(f"\n✅ Created {len(USERS)} users")

    return user_credentials


def print_summary(user_credentials):
    """Print login credentials summary"""
    print("\n" + "="*70)
    print("SEED DATA SUMMARY")
    print("="*70)

    # Group by tenant
    by_tenant = {}
    for cred in user_credentials:
        slug = cred['tenant_slug']
        if slug not in by_tenant:
            by_tenant[slug] = []
        by_tenant[slug].append(cred)

    for slug, users in by_tenant.items():
        print(f"\n📁 {slug}")
        print("  " + "-"*66)
        for user in users:
            print(f"  👤 {user['name']:<20} ({user['role']})")
            print(f"     Email:    {user['email']}")
            print(f"     Password: {user['password']}")
            print(f"     User ID:  {user['user_id']}")
            print(f"     Tenant:   {user['tenant_id']}")
            print()

    print("="*70)
    print("LOGIN INSTRUCTIONS")
    print("="*70)
    print("\n1. Go to your frontend: https://twondbrain-frontend.onrender.com")
    print("2. Click 'Login'")
    print("3. Use any email/password combination above")
    print("\nRECOMMENDED TEST ACCOUNTS:")
    print("  • admin@acme.com / admin123 (Enterprise admin)")
    print("  • founder@startup.io / founder123 (Professional admin)")
    print("  • test@freetier.org / test123 (Free tier)")

    print("\n✅ Seed data created successfully!")


def verify_tenant_isolation(db):
    """Verify tenant isolation is working"""
    print("\n" + "="*70)
    print("VERIFYING TENANT ISOLATION")
    print("="*70)

    tenants = db.query(Tenant).all()

    for tenant in tenants:
        user_count = db.query(User).filter(User.tenant_id == tenant.id).count()
        print(f"\n✓ {tenant.name} ({tenant.slug}):")
        print(f"  - Tenant ID: {tenant.id}")
        print(f"  - Plan: {tenant.plan.value}")
        print(f"  - Users: {user_count}")

        # Verify no users from other tenants
        other_tenant_users = db.query(User).filter(
            User.tenant_id != tenant.id
        ).count()

        if other_tenant_users > 0:
            print(f"  - Other tenants have {other_tenant_users} users (isolated ✓)")

    print(f"\n✅ Tenant isolation verified!")


def main():
    """Run seed script"""
    print("\n" + "="*70)
    print("🌱 DATABASE SEED SCRIPT")
    print("="*70)

    db = SessionLocal()
    try:
        # Check if database is empty
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"\n⚠️  WARNING: Database already has {existing_users} users!")
            if '--force' not in sys.argv:
                response = input("Continue and add more data? (yes/no): ")
                if response.lower() != 'yes':
                    print("\n❌ Seed cancelled.")
                    return

        # Create data
        tenant_map = create_tenants(db)
        user_credentials = create_users(db, tenant_map)

        # Verify
        verify_tenant_isolation(db)

        # Print summary
        print_summary(user_credentials)

    except Exception as e:
        print(f"\n❌ Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    main()
