'use client'

import React, { useState } from 'react'
import Sidebar from '../shared/Sidebar'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

export default function Settings() {
  const [activeItem, setActiveItem] = useState('Settings')
  const [loggingOut, setLoggingOut] = useState(false)
  const router = useRouter()
  const { logout } = useAuth()

  const handleLogout = async () => {
    setLoggingOut(true)
    try {
      await logout()
      router.push('/login')
    } catch (error) {
      console.error('Logout failed:', error)
      // Still redirect even if logout call fails
      router.push('/login')
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-8 py-6 bg-primary">
          <h1
            style={{
              color: '#081028',
              fontFamily: '"Work Sans", sans-serif',
              fontSize: '36px',
              fontWeight: 600,
              letterSpacing: '-0.72px'
            }}
          >
            Settings
          </h1>
        </div>

        {/* Content */}
        <div className="flex-1 px-8 py-6 bg-primary overflow-auto">
          <div className="max-w-2xl">
            <div className="mb-8">
              <h2
                style={{
                  color: '#081028',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '20px',
                  fontWeight: 600,
                  marginBottom: '16px'
                }}
              >
                Account
              </h2>
              
              <button
                onClick={handleLogout}
                disabled={loggingOut}
                style={{
                  display: 'flex',
                  padding: '12px 24px',
                  justifyContent: 'center',
                  alignItems: 'center',
                  borderRadius: '8px',
                  backgroundColor: '#FFE2BF',
                  border: '1px solid #081028',
                  cursor: loggingOut ? 'not-allowed' : 'pointer',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '16px',
                  fontWeight: 500,
                  color: '#081028',
                  boxShadow: '0 4px 4px 0 rgba(0, 0, 0, 0.25)',
                  opacity: loggingOut ? 0.6 : 1
                }}
              >
                {loggingOut ? 'Logging out...' : 'Logout'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
