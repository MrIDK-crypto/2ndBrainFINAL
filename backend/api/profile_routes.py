"""
User Profile API Routes
Endpoints for managing user profiles, avatars, passwords, and preferences.
"""

import os
import uuid
from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from services.auth_service import require_auth, PasswordUtils
from database.models import SessionLocal, User
from services.s3_service import S3Service

profile_bp = Blueprint('profile', __name__, url_prefix='/api/profile')


# ============================================================================
# GET PROFILE
# ============================================================================

@profile_bp.route('/', methods=['GET'])
@require_auth
def get_profile():
    """
    Get current user's profile.

    GET /api/profile

    Returns:
        {
            "success": true,
            "user": {
                "id": "...",
                "email": "...",
                "full_name": "...",
                "avatar_url": "...",
                "bio": "...",
                "phone": "...",
                "job_title": "...",
                "department": "...",
                "location": "...",
                "timezone": "UTC",
                "language": "en",
                "date_format": "YYYY-MM-DD",
                "time_format": "24h",
                "role": "member",
                "email_verified": true,
                "mfa_enabled": false,
                "preferences": {},
                "created_at": "...",
                "updated_at": "..."
            }
        }
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        return jsonify({
            'success': True,
            'user': user.to_dict()
        })

    finally:
        db.close()


# ============================================================================
# UPDATE PROFILE
# ============================================================================

@profile_bp.route('/', methods=['PUT'])
@require_auth
def update_profile():
    """
    Update current user's profile.

    PUT /api/profile

    Request body:
    {
        "full_name": "John Doe",
        "bio": "Software Engineer passionate about AI",
        "phone": "+1-555-0123",
        "job_title": "Senior Engineer",
        "department": "Engineering",
        "location": "San Francisco, CA",
        "timezone": "America/Los_Angeles",
        "language": "en",
        "date_format": "MM/DD/YYYY",
        "time_format": "12h"
    }

    Returns:
        {
            "success": true,
            "user": {...},
            "message": "Profile updated successfully"
        }
    """
    data = request.get_json() or {}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Updateable fields
        updateable_fields = [
            'full_name', 'bio', 'phone', 'job_title',
            'department', 'location', 'timezone', 'language',
            'date_format', 'time_format'
        ]

        updated_fields = []
        for field in updateable_fields:
            if field in data:
                setattr(user, field, data[field])
                updated_fields.append(field)

        db.commit()

        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'message': 'Profile updated successfully',
            'updated_fields': updated_fields
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()


# ============================================================================
# UPLOAD AVATAR
# ============================================================================

@profile_bp.route('/avatar', methods=['POST'])
@require_auth
def upload_avatar():
    """
    Upload user avatar image.

    POST /api/profile/avatar
    Content-Type: multipart/form-data

    Form data:
        avatar: <file> (image file, max 5MB)

    Supported formats: jpg, jpeg, png, gif, webp

    Returns:
        {
            "success": true,
            "avatar_url": "https://s3.amazonaws.com/...",
            "message": "Avatar uploaded successfully"
        }
    """
    if 'avatar' not in request.files:
        return jsonify({
            'success': False,
            'error': 'No avatar file provided'
        }), 400

    file = request.files['avatar']

    if file.filename == '':
        return jsonify({
            'success': False,
            'error': 'No file selected'
        }), 400

    # Validate file type
    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
        }), 400

    # Validate file size (max 5MB)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning

    if file_size > 5 * 1024 * 1024:  # 5MB
        return jsonify({
            'success': False,
            'error': 'File too large. Maximum size: 5MB'
        }), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Generate unique filename
        s3_key = f"avatars/{g.tenant_id}/{g.user_id}_{uuid.uuid4()}.{file_ext}"

        # Upload to S3
        from services.s3_service import get_s3_service
        s3_service = get_s3_service()

        # Read file bytes
        file_bytes = file.read()

        avatar_url, error = s3_service.upload_bytes(
            file_bytes=file_bytes,
            s3_key=s3_key,
            content_type=file.content_type
        )

        if error:
            raise Exception(error)

        # Delete old avatar from S3 if exists
        if user.avatar_url and user.avatar_url.startswith('http'):
            try:
                # Extract S3 key from URL
                # URL format: https://bucket.s3.region.amazonaws.com/avatars/tenant_id/filename
                url_parts = user.avatar_url.split('/')
                if len(url_parts) >= 3:
                    old_s3_key = '/'.join(url_parts[-3:])  # avatars/tenant_id/filename
                    s3_service.delete_file(old_s3_key)
            except Exception as e:
                print(f"[Profile] Error deleting old avatar: {e}")

        # Update user avatar_url
        user.avatar_url = avatar_url
        db.commit()

        return jsonify({
            'success': True,
            'avatar_url': avatar_url,
            'message': 'Avatar uploaded successfully'
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()


@profile_bp.route('/avatar', methods=['DELETE'])
@require_auth
def delete_avatar():
    """
    Delete user avatar (set to null).

    DELETE /api/profile/avatar

    Returns:
        {
            "success": true,
            "message": "Avatar deleted successfully"
        }
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Delete from S3 if exists
        if user.avatar_url and user.avatar_url.startswith('http'):
            try:
                from services.s3_service import get_s3_service
                s3_service = get_s3_service()
                # Extract S3 key from URL
                url_parts = user.avatar_url.split('/')
                if len(url_parts) >= 3:
                    s3_key = '/'.join(url_parts[-3:])  # avatars/tenant_id/filename
                    s3_service.delete_file(s3_key)
            except Exception as e:
                print(f"[Profile] Error deleting avatar from S3: {e}")

        # Clear avatar_url
        user.avatar_url = None
        db.commit()

        return jsonify({
            'success': True,
            'message': 'Avatar deleted successfully'
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()


# ============================================================================
# CHANGE PASSWORD
# ============================================================================

@profile_bp.route('/password', methods=['PUT'])
@require_auth
def change_password():
    """
    Change user password.

    PUT /api/profile/password

    Request body:
    {
        "current_password": "old_password123",
        "new_password": "new_password456"
    }

    Returns:
        {
            "success": true,
            "message": "Password changed successfully"
        }
    """
    data = request.get_json() or {}

    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({
            'success': False,
            'error': 'Current password and new password are required'
        }), 400

    # Validate new password strength
    if len(new_password) < 8:
        return jsonify({
            'success': False,
            'error': 'New password must be at least 8 characters'
        }), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Verify current password
        if not PasswordUtils.verify_password(current_password, user.password_hash):
            return jsonify({
                'success': False,
                'error': 'Current password is incorrect'
            }), 401

        # Hash new password
        new_password_hash = PasswordUtils.hash_password(new_password)

        # Update password
        user.password_hash = new_password_hash
        db.commit()

        # Optional: Revoke all existing sessions (force re-login)
        # from database.models import UserSession
        # db.query(UserSession).filter(UserSession.user_id == user.id).update({'is_revoked': True})
        # db.commit()

        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()


# ============================================================================
# PREFERENCES
# ============================================================================

@profile_bp.route('/preferences', methods=['GET'])
@require_auth
def get_preferences():
    """
    Get user preferences.

    GET /api/profile/preferences

    Returns:
        {
            "success": true,
            "preferences": {
                "notifications_email": true,
                "notifications_push": true,
                "theme": "dark",
                "sidebar_collapsed": false,
                ...
            }
        }
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        return jsonify({
            'success': True,
            'preferences': user.preferences or {}
        })

    finally:
        db.close()


@profile_bp.route('/preferences', methods=['PUT'])
@require_auth
def update_preferences():
    """
    Update user preferences (merge with existing).

    PUT /api/profile/preferences

    Request body:
    {
        "theme": "dark",
        "notifications_email": true,
        "notifications_push": false,
        "sidebar_collapsed": true,
        "default_view": "grid"
    }

    Returns:
        {
            "success": true,
            "preferences": {...},
            "message": "Preferences updated successfully"
        }
    """
    data = request.get_json() or {}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Merge with existing preferences
        current_prefs = user.preferences or {}
        current_prefs.update(data)

        user.preferences = current_prefs
        db.commit()

        return jsonify({
            'success': True,
            'preferences': current_prefs,
            'message': 'Preferences updated successfully'
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()


# ============================================================================
# ACCOUNT DELETION (Optional)
# ============================================================================

@profile_bp.route('/delete-account', methods=['POST'])
@require_auth
def delete_account():
    """
    Delete user account (soft delete).

    POST /api/profile/delete-account

    Request body:
    {
        "password": "user_password",
        "confirmation": "DELETE MY ACCOUNT"
    }

    Returns:
        {
            "success": true,
            "message": "Account deleted successfully"
        }
    """
    data = request.get_json() or {}

    password = data.get('password')
    confirmation = data.get('confirmation')

    if confirmation != 'DELETE MY ACCOUNT':
        return jsonify({
            'success': False,
            'error': 'Invalid confirmation. Please type: DELETE MY ACCOUNT'
        }), 400

    if not password:
        return jsonify({
            'success': False,
            'error': 'Password required'
        }), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == g.user_id).first()

        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

        # Verify password
        if not PasswordUtils.verify_password(password, user.password_hash):
            return jsonify({
                'success': False,
                'error': 'Incorrect password'
            }), 401

        # Soft delete (mark as inactive)
        user.is_active = False
        user.email = f"deleted_{user.id}@deleted.com"  # Anonymize email

        # Revoke all sessions
        from database.models import UserSession
        db.query(UserSession).filter(UserSession.user_id == user.id).update({'is_revoked': True})

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Account deleted successfully'
        })

    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()
