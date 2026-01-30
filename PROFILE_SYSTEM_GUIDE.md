# User Profile System - Complete Guide

## Overview

I've created a comprehensive user profile system with:
- ✅ **Extended user profiles** (bio, phone, job title, location, etc.)
- ✅ **Avatar upload to S3** (with automatic old avatar deletion)
- ✅ **Password change** (with current password verification)
- ✅ **User preferences** (theme, notifications, etc.)
- ✅ **Account deletion** (soft delete with confirmation)
- ✅ **All endpoints secured** with JWT authentication

---

## User Model Enhancements

### New Fields Added

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `bio` | Text | User biography/description | null |
| `phone` | String(20) | Phone number | null |
| `job_title` | String(100) | Job title/position | null |
| `department` | String(100) | Department/team | null |
| `location` | String(255) | City, Country | null |
| `language` | String(10) | ISO 639-1 language code | "en" |
| `date_format` | String(20) | Preferred date format | "YYYY-MM-DD" |
| `time_format` | String(10) | Time format (12h/24h) | "24h" |

### Existing Fields

- `id` - UUID
- `tenant_id` - Foreign key to tenant
- `email` - Email address
- `full_name` - Full name
- `avatar_url` - S3 URL to avatar image
- `timezone` - User timezone (default: UTC)
- `role` - UserRole enum (Admin, Member, Viewer)
- `preferences` - JSON object for custom preferences
- `email_verified` - Boolean
- `mfa_enabled` - Boolean
- `created_at` - Timestamp
- `updated_at` - Timestamp
- `is_active` - Boolean

---

## API Endpoints

Base URL: `https://twondbrain-backend-docker.onrender.com`

All endpoints require JWT authentication via `Authorization: Bearer {token}` header.

###

 1. **GET /api/profile**

Get current user's complete profile.

**Request:**
```bash
curl -X GET https://twondbrain-backend-docker.onrender.com/api/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "660e8400-e29b-41d4-a716-446655440000",
    "email": "admin@acme.com",
    "full_name": "Alice Admin",
    "avatar_url": "https://bucket.s3.amazonaws.com/avatars/tenant/file.jpg",
    "bio": "Senior Engineering Manager",
    "phone": "+1-555-0123",
    "job_title": "Engineering Manager",
    "department": "Engineering",
    "location": "San Francisco, CA",
    "timezone": "America/Los_Angeles",
    "language": "en",
    "date_format": "MM/DD/YYYY",
    "time_format": "12h",
    "role": "admin",
    "email_verified": true,
    "mfa_enabled": false,
    "preferences": {
      "theme": "dark",
      "notifications_email": true
    },
    "created_at": "2026-01-30T00:00:00Z",
    "updated_at": "2026-01-30T12:00:00Z",
    "is_active": true
  }
}
```

---

### 2. **PUT /api/profile**

Update user profile fields.

**Request:**
```bash
curl -X PUT https://twondbrain-backend-docker.onrender.com/api/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Alice Administrator",
    "bio": "Engineering leader with 10+ years experience",
    "phone": "+1-555-0199",
    "job_title": "VP of Engineering",
    "department": "Engineering",
    "location": "San Francisco, CA",
    "timezone": "America/Los_Angeles",
    "language": "en",
    "date_format": "MM/DD/YYYY",
    "time_format": "12h"
  }'
```

**Updateable Fields:**
- `full_name`
- `bio`
- `phone`
- `job_title`
- `department`
- `location`
- `timezone`
- `language`
- `date_format`
- `time_format`

**Response:**
```json
{
  "success": true,
  "user": { ... },
  "message": "Profile updated successfully",
  "updated_fields": ["full_name", "bio", "job_title"]
}
```

---

### 3. **POST /api/profile/avatar**

Upload user avatar image.

**Request:**
```bash
curl -X POST https://twondbrain-backend-docker.onrender.com/api/profile/avatar \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "avatar=@/path/to/image.jpg"
```

**File Requirements:**
- **Max size**: 5MB
- **Formats**: jpg, jpeg, png, gif, webp
- **Storage**: S3 at `avatars/{tenant_id}/{user_id}_{uuid}.{ext}`

**Response:**
```json
{
  "success": true,
  "avatar_url": "https://catalyst-uploads-pranav.s3.us-east-2.amazonaws.com/avatars/tenant123/user456_abc123.jpg",
  "message": "Avatar uploaded successfully"
}
```

**Automatic Cleanup:**
- Old avatar is automatically deleted from S3 when new one is uploaded

---

### 4. **DELETE /api/profile/avatar**

Delete user avatar.

**Request:**
```bash
curl -X DELETE https://twondbrain-backend-docker.onrender.com/api/profile/avatar \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "message": "Avatar deleted successfully"
}
```

**What Happens:**
- Avatar file deleted from S3
- `avatar_url` set to `null` in database

---

### 5. **PUT /api/profile/password**

Change user password.

**Request:**
```bash
curl -X PUT https://twondbrain-backend-docker.onrender.com/api/profile/password \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "oldPassword123",
    "new_password": "newPassword456"
  }'
```

**Validation:**
- Current password must be correct
- New password must be at least 8 characters

**Response:**
```json
{
  "success": true,
  "message": "Password changed successfully"
}
```

**Security:**
- ✅ Requires current password verification
- ✅ New password hashed with bcrypt
- ✅ Min 8 characters enforced
- ⚠️  Optional: Could revoke all sessions (force re-login)

---

### 6. **GET /api/profile/preferences**

Get user preferences.

**Request:**
```bash
curl -X GET https://twondbrain-backend-docker.onrender.com/api/profile/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "preferences": {
    "theme": "dark",
    "notifications_email": true,
    "notifications_push": false,
    "sidebar_collapsed": true,
    "default_view": "grid",
    "language": "en"
  }
}
```

---

### 7. **PUT /api/profile/preferences**

Update user preferences (merged with existing).

**Request:**
```bash
curl -X PUT https://twondbrain-backend-docker.onrender.com/api/profile/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "theme": "dark",
    "notifications_email": true,
    "sidebar_collapsed": false
  }'
```

**Response:**
```json
{
  "success": true,
  "preferences": {
    "theme": "dark",
    "notifications_email": true,
    "notifications_push": false,
    "sidebar_collapsed": false,
    "default_view": "grid",
    "language": "en"
  },
  "message": "Preferences updated successfully"
}
```

**How It Works:**
- Preferences are **merged** with existing preferences
- Only provided keys are updated
- Other preferences remain unchanged

---

### 8. **POST /api/profile/delete-account**

Delete user account (soft delete).

**Request:**
```bash
curl -X POST https://twondbrain-backend-docker.onrender.com/api/profile/delete-account \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "password": "userPassword123",
    "confirmation": "DELETE MY ACCOUNT"
  }'
```

**Requirements:**
- Must provide correct password
- Must type **exactly**: `DELETE MY ACCOUNT`

**Response:**
```json
{
  "success": true,
  "message": "Account deleted successfully"
}
```

**What Happens:**
- ✅ User marked as inactive (`is_active = false`)
- ✅ Email anonymized (`deleted_{user_id}@deleted.com`)
- ✅ All sessions revoked
- ⚠️  **This is a soft delete** - data remains for audit purposes

---

## Frontend Integration

### Install Dependencies

```bash
cd frontend
npm install axios
```

### Create Profile Settings Page

Here's a complete React/Next.js profile settings component:

```typescript
// frontend/app/profile/page.tsx

'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003';

interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string;
  bio?: string;
  phone?: string;
  job_title?: string;
  department?: string;
  location?: string;
  timezone: string;
  language: string;
  date_format: string;
  time_format: string;
  role: string;
}

export default function ProfileSettings() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    full_name: '',
    bio: '',
    phone: '',
    job_title: '',
    department: '',
    location: '',
    timezone: 'UTC',
    language: 'en',
    date_format: 'YYYY-MM-DD',
    time_format: '24h'
  });

  // Password change state
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: ''
  });

  // Load profile
  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.get(`${API_BASE}/api/profile`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const user = response.data.user;
      setProfile(user);
      setFormData({
        full_name: user.full_name || '',
        bio: user.bio || '',
        phone: user.phone || '',
        job_title: user.job_title || '',
        department: user.department || '',
        location: user.location || '',
        timezone: user.timezone || 'UTC',
        language: user.language || 'en',
        date_format: user.date_format || 'YYYY-MM-DD',
        time_format: user.time_format || '24h'
      });
      setLoading(false);
    } catch (error) {
      console.error('Error loading profile:', error);
      setLoading(false);
    }
  };

  const handleUpdateProfile = async () => {
    setSaving(true);
    setMessage('');

    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.put(
        `${API_BASE}/api/profile`,
        formData,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      setProfile(response.data.user);
      setMessage('Profile updated successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (error: any) {
      setMessage(`Error: ${error.response?.data?.error || 'Failed to update profile'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('avatar', file);

    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.post(
        `${API_BASE}/api/profile/avatar`,
        formData,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      setMessage('Avatar uploaded successfully!');
      loadProfile(); // Reload to get new avatar URL
      setTimeout(() => setMessage(''), 3000);
    } catch (error: any) {
      setMessage(`Error: ${error.response?.data?.error || 'Failed to upload avatar'}`);
    }
  };

  const handleChangePassword = async () => {
    if (!passwordData.current_password || !passwordData.new_password) {
      setMessage('Please fill in both password fields');
      return;
    }

    try {
      const token = localStorage.getItem('access_token');
      await axios.put(
        `${API_BASE}/api/profile/password`,
        passwordData,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      setMessage('Password changed successfully!');
      setPasswordData({ current_password: '', new_password: '' });
      setTimeout(() => setMessage(''), 3000);
    } catch (error: any) {
      setMessage(`Error: ${error.response?.data?.error || 'Failed to change password'}`);
    }
  };

  if (loading) {
    return <div className="p-8">Loading profile...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">Profile Settings</h1>

      {message && (
        <div className={`p-4 mb-6 rounded ${message.includes('Error') ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
          {message}
        </div>
      )}

      {/* Avatar Section */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Profile Picture</h2>
        <div className="flex items-center gap-6">
          {profile?.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt="Avatar"
              className="w-24 h-24 rounded-full object-cover"
            />
          ) : (
            <div className="w-24 h-24 rounded-full bg-gray-200 flex items-center justify-center text-3xl font-bold text-gray-600">
              {profile?.full_name?.[0] || 'U'}
            </div>
          )}
          <div>
            <label className="block">
              <span className="sr-only">Choose avatar</span>
              <input
                type="file"
                accept="image/*"
                onChange={handleAvatarUpload}
                className="block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded file:border-0
                  file:text-sm file:font-semibold
                  file:bg-blue-50 file:text-blue-700
                  hover:file:bg-blue-100"
              />
            </label>
            <p className="text-sm text-gray-500 mt-2">
              JPG, PNG, GIF or WEBP. Max 5MB.
            </p>
          </div>
        </div>
      </div>

      {/* Profile Information */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Profile Information</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Full Name
            </label>
            <input
              type="text"
              value={formData.full_name}
              onChange={(e) => setFormData({...formData, full_name: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Email (read-only)
            </label>
            <input
              type="email"
              value={profile?.email || ''}
              disabled
              className="w-full px-3 py-2 border rounded-lg bg-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Phone
            </label>
            <input
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({...formData, phone: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Job Title
            </label>
            <input
              type="text"
              value={formData.job_title}
              onChange={(e) => setFormData({...formData, job_title: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Department
            </label>
            <input
              type="text"
              value={formData.department}
              onChange={(e) => setFormData({...formData, department: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Location
            </label>
            <input
              type="text"
              value={formData.location}
              onChange={(e) => setFormData({...formData, location: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
              placeholder="San Francisco, CA"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Bio
            </label>
            <textarea
              value={formData.bio}
              onChange={(e) => setFormData({...formData, bio: e.target.value})}
              rows={3}
              className="w-full px-3 py-2 border rounded-lg"
              placeholder="Tell us about yourself..."
            />
          </div>
        </div>

        <button
          onClick={handleUpdateProfile}
          disabled={saving}
          className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
        >
          {saving ? 'Saving...' : 'Save Profile'}
        </button>
      </div>

      {/* Change Password */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Change Password</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Current Password
            </label>
            <input
              type="password"
              value={passwordData.current_password}
              onChange={(e) => setPasswordData({...passwordData, current_password: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              New Password
            </label>
            <input
              type="password"
              value={passwordData.new_password}
              onChange={(e) => setPasswordData({...passwordData, new_password: e.target.value})}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>
        </div>

        <button
          onClick={handleChangePassword}
          className="mt-6 px-6 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-900"
        >
          Change Password
        </button>
      </div>
    </div>
  );
}
```

---

## Testing the Profile System

### 1. Test with Postman/cURL

```bash
# Get JWT token first
TOKEN=$(curl -X POST http://localhost:5003/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@acme.com", "password": "admin123"}' \
  | jq -r '.access_token')

# Get profile
curl -X GET http://localhost:5003/api/profile \
  -H "Authorization: Bearer $TOKEN"

# Update profile
curl -X PUT http://localhost:5003/api/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Alice Updated", "bio": "New bio"}'

# Upload avatar
curl -X POST http://localhost:5003/api/profile/avatar \
  -H "Authorization: Bearer $TOKEN" \
  -F "avatar=@avatar.jpg"
```

### 2. Test from Frontend

1. Create the profile settings page (code above)
2. Add link to navigation: `/profile`
3. Login with test account
4. Navigate to profile settings
5. Update fields and upload avatar

---

## Security Considerations

✅ **All endpoints require JWT authentication**
✅ **Password changes require current password**
✅ **Account deletion requires confirmation text**
✅ **Avatar uploads validated (type, size)**
✅ **S3 uploads are tenant-isolated**
✅ **Soft delete preserves data for audit**
✅ **Old avatars auto-deleted to save storage**

---

## Next Steps

1. ✅ **Backend complete** - All API endpoints working
2. ⚠️ **Frontend needed**:
   - Create profile settings page
   - Add avatar upload UI
   - Add password change form
   - Add preferences toggles

3. ⚠️ **Optional enhancements**:
   - Email change (with verification)
   - Two-factor authentication (MFA)
   - Session management (view/revoke sessions)
   - Activity log

---

**Created**: 2026-01-30
**Status**: Backend Complete ✅, Frontend Pending ⚠️
