'use client'

import React, { useState, useEffect } from 'react'
import Sidebar from '../shared/Sidebar'
import Image from 'next/image'
import axios from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : 'http://localhost:5003/api'

interface Integration {
  id: string
  name: string
  logo: string
  description: string
  category: string
  connected: boolean
  isOAuth?: boolean
}

interface SlackChannel {
  id: string
  name: string
  is_private: boolean
  is_member: boolean
  member_count: number
  selected: boolean
}

// Channel Selection Modal Component
const ChannelSelectionModal = ({
  isOpen,
  onClose,
  channels,
  onSave,
  isLoading
}: {
  isOpen: boolean
  onClose: () => void
  channels: SlackChannel[]
  onSave: (selectedIds: string[]) => void
  isLoading: boolean
}) => {
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set())

  useEffect(() => {
    // Initialize with already selected channels
    const selected = new Set(channels.filter(c => c.selected).map(c => c.id))
    setSelectedChannels(selected)
  }, [channels])

  const toggleChannel = (id: string) => {
    setSelectedChannels(prev => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }

  const selectAll = () => {
    setSelectedChannels(new Set(channels.map(c => c.id)))
  }

  const selectNone = () => {
    setSelectedChannels(new Set())
  }

  if (!isOpen) return null

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#FFF3E4',
          borderRadius: '16px',
          padding: '32px',
          maxWidth: '500px',
          width: '90%',
          maxHeight: '80vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
        onClick={e => e.stopPropagation()}
      >
        <h2 style={{
          fontFamily: 'Geist, sans-serif',
          fontSize: '24px',
          fontWeight: 600,
          marginBottom: '8px',
          color: '#18181B'
        }}>
          Select Slack Channels
        </h2>
        <p style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '14px',
          color: '#71717A',
          marginBottom: '16px'
        }}>
          Choose which channels to sync to your knowledge base. Only messages from selected channels will be imported.
        </p>

        {/* Quick select buttons */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <button
            onClick={selectAll}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #D4D4D8',
              backgroundColor: '#fff',
              fontSize: '12px',
              cursor: 'pointer'
            }}
          >
            Select All
          </button>
          <button
            onClick={selectNone}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #D4D4D8',
              backgroundColor: '#fff',
              fontSize: '12px',
              cursor: 'pointer'
            }}
          >
            Select None
          </button>
          <span style={{
            marginLeft: 'auto',
            fontSize: '12px',
            color: '#71717A',
            alignSelf: 'center'
          }}>
            {selectedChannels.size} of {channels.length} selected
          </span>
        </div>

        {/* Channel list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          border: '1px solid #D4D4D8',
          borderRadius: '8px',
          backgroundColor: '#fff'
        }}>
          {channels.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: '#71717A' }}>
              {isLoading ? 'Loading channels...' : 'No channels found'}
            </div>
          ) : (
            channels.map(channel => (
              <div
                key={channel.id}
                onClick={() => toggleChannel(channel.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px 16px',
                  borderBottom: '1px solid #E4E4E7',
                  cursor: 'pointer',
                  backgroundColor: selectedChannels.has(channel.id) ? '#E0F2FE' : 'transparent'
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedChannels.has(channel.id)}
                  onChange={() => {}}
                  style={{ marginRight: '12px', cursor: 'pointer' }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    color: '#18181B'
                  }}>
                    {channel.is_private ? '🔒' : '#'} {channel.name}
                  </div>
                  <div style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '12px',
                    color: '#71717A'
                  }}>
                    {channel.member_count} members
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Action buttons */}
        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '12px',
          marginTop: '24px'
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid #D4D4D8',
              backgroundColor: '#fff',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(Array.from(selectedChannels))}
            disabled={selectedChannels.size === 0}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: selectedChannels.size === 0 ? '#9ca3af' : '#4A154B',
              color: '#fff',
              fontSize: '14px',
              fontWeight: 500,
              cursor: selectedChannels.size === 0 ? 'not-allowed' : 'pointer'
            }}
          >
            Save & Sync ({selectedChannels.size} channels)
          </button>
        </div>
      </div>
    </div>
  )
}

// Sync Progress Modal Component
interface SyncProgress {
  integration: string
  status: 'starting' | 'syncing' | 'parsing' | 'embedding' | 'completed' | 'error'
  progress: number
  documentsFound: number
  documentsParsed: number
  documentsEmbedded: number
  currentFile?: string
  error?: string
  startTime?: number
}

// Helper to save/load sync state from localStorage
const SYNC_STATE_KEY = '2ndbrain_sync_state'
const CONNECTED_INTEGRATIONS_KEY = '2ndbrain_connected_integrations'

const saveSyncState = (state: {
  integration: string;
  startTime?: number;
  status?: string;
  progress?: number;
  documentsFound?: number;
  documentsParsed?: number;
  documentsEmbedded?: number;
  completedAt?: number;
} | null) => {
  if (typeof window === 'undefined') return
  if (state) {
    localStorage.setItem(SYNC_STATE_KEY, JSON.stringify(state))
  } else {
    localStorage.removeItem(SYNC_STATE_KEY)
  }
}

const loadSyncState = (): {
  integration: string;
  startTime?: number;
  status?: string;
  progress?: number;
  documentsFound?: number;
  documentsParsed?: number;
  documentsEmbedded?: number;
  completedAt?: number;
} | null => {
  if (typeof window === 'undefined') return null
  try {
    const saved = localStorage.getItem(SYNC_STATE_KEY)
    return saved ? JSON.parse(saved) : null
  } catch {
    return null
  }
}

// Save/load connected integrations to localStorage for persistence
const saveConnectedIntegrations = (connectedIds: string[]) => {
  if (typeof window === 'undefined') return
  localStorage.setItem(CONNECTED_INTEGRATIONS_KEY, JSON.stringify(connectedIds))
}

const loadConnectedIntegrations = (): string[] => {
  if (typeof window === 'undefined') return []
  try {
    const saved = localStorage.getItem(CONNECTED_INTEGRATIONS_KEY)
    return saved ? JSON.parse(saved) : []
  } catch {
    return []
  }
}

// Animated counter component
const AnimatedCounter = ({ value, label }: { value: number; label: string }) => {
  const [displayValue, setDisplayValue] = useState(value)
  const [isAnimating, setIsAnimating] = useState(false)

  useEffect(() => {
    if (value !== displayValue) {
      setIsAnimating(true)
      // Animate the counter
      const duration = 300
      const startValue = displayValue
      const startTime = Date.now()

      const animate = () => {
        const elapsed = Date.now() - startTime
        const progress = Math.min(elapsed / duration, 1)
        const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
        const current = Math.round(startValue + (value - startValue) * eased)
        setDisplayValue(current)

        if (progress < 1) {
          requestAnimationFrame(animate)
        } else {
          setIsAnimating(false)
        }
      }
      requestAnimationFrame(animate)
    }
  }, [value, displayValue])

  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{
        fontFamily: '"Work Sans", sans-serif',
        fontSize: '20px',
        fontWeight: 600,
        color: '#18181B',
        transform: isAnimating ? 'scale(1.1)' : 'scale(1)',
        transition: 'transform 0.15s ease-out'
      }}>
        {displayValue}
      </div>
      <div style={{
        fontFamily: '"Work Sans", sans-serif',
        fontSize: '11px',
        color: '#9CA3AF',
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        {label}
      </div>
    </div>
  )
}

const SyncProgressModal = ({
  isOpen,
  onClose,
  progress,
  onMinimize,
  syncStartTime
}: {
  isOpen: boolean
  onClose: () => void
  progress: SyncProgress | null
  onMinimize?: () => void
  syncStartTime?: number
}) => {
  // Track progress history for better time estimation
  const [progressHistory, setProgressHistory] = useState<{time: number, progress: number}[]>([])
  const [estimatedSeconds, setEstimatedSeconds] = useState<number | null>(null)

  // Update progress history when progress changes
  useEffect(() => {
    if (progress && progress.progress > 0) {
      const now = Date.now()
      setProgressHistory(prev => {
        const newHistory = [...prev, { time: now, progress: progress.progress }]
        // Keep last 10 data points for smoothing
        return newHistory.slice(-10)
      })
    }
  }, [progress?.progress])

  // Calculate estimated time with phase-aware timing
  // Progress phases (backend):
  // 0-40%: syncing (fast - fetching files)
  // 40-70%: parsing (medium - saving to DB)
  // 70-95%: embedding (SLOW - GPT extraction + Pinecone)
  // 95-100%: finishing
  useEffect(() => {
    if (!progress || progress.status === 'completed' || progress.status === 'error') {
      setEstimatedSeconds(null)
      return
    }

    // Phase-specific time multipliers (seconds per 1% progress)
    const getPhaseMultiplier = (currentProgress: number, status: string): number => {
      // Embedding phase is much slower due to GPT extraction calls
      if (status === 'embedding' || currentProgress >= 70) {
        // Each percent in embedding phase takes ~5-10 seconds (GPT + Pinecone)
        return 6.0
      }
      // Parsing phase is moderate
      if (status === 'parsing' || currentProgress >= 40) {
        return 1.5
      }
      // Syncing phase is fast
      return 0.5
    }

    // Early estimate for starting
    if (progress.status === 'starting' || progress.progress < 3) {
      // Better initial estimate based on typical full sync
      const docsFound = progress.documentsFound || 10
      // Estimate: syncing 40% fast + parsing 30% medium + embedding 25% slow
      const estimatedTotal = (40 * 0.5) + (30 * 1.5) + (25 * 6.0 * (docsFound / 10))
      setEstimatedSeconds(Math.max(estimatedTotal, 60))
      return
    }

    const currentProgress = progress.progress || 0
    const remaining = 100 - currentProgress

    // Calculate remaining time based on phase-aware estimates
    let estimatedRemaining = 0

    if (currentProgress < 40) {
      // In syncing phase
      const syncRemaining = 40 - currentProgress
      const parseRemaining = 30
      const embedRemaining = 25
      const docsFound = progress.documentsFound || 10
      estimatedRemaining = (syncRemaining * 0.5) + (parseRemaining * 1.5) + (embedRemaining * 6.0 * Math.max(1, docsFound / 10))
    } else if (currentProgress < 70) {
      // In parsing phase
      const parseRemaining = 70 - currentProgress
      const embedRemaining = 25
      const docsFound = progress.documentsFound || 10
      estimatedRemaining = (parseRemaining * 1.5) + (embedRemaining * 6.0 * Math.max(1, docsFound / 10))
    } else if (currentProgress < 95) {
      // In embedding phase (slowest)
      const embedRemaining = 95 - currentProgress
      const docsFound = progress.documentsFound || 10
      // GPT extraction is about 3-5 seconds per doc, embedding is 1-2 seconds per doc
      estimatedRemaining = embedRemaining * 6.0 * Math.max(1, docsFound / 10)
    } else {
      // Finishing up
      estimatedRemaining = (100 - currentProgress) * 0.5
    }

    // Use history for rate-based refinement if available
    if (progressHistory.length >= 3) {
      const oldest = progressHistory[0]
      const newest = progressHistory[progressHistory.length - 1]
      const timeDiff = (newest.time - oldest.time) / 1000
      const progressDiff = newest.progress - oldest.progress

      if (timeDiff > 2 && progressDiff > 0) {
        const observedRate = progressDiff / timeDiff
        const phaseMultiplier = getPhaseMultiplier(currentProgress, progress.status)
        const adjustedRate = observedRate / phaseMultiplier

        // Weight observed rate against phase-based estimate
        if (adjustedRate > 0) {
          const rateBasedEstimate = remaining / adjustedRate
          // Blend: 60% phase-based, 40% observed rate
          estimatedRemaining = estimatedRemaining * 0.6 + rateBasedEstimate * 0.4
        }
      }
    }

    // Smooth transitions to avoid jumpy numbers
    if (estimatedRemaining > 0 && estimatedRemaining < 86400) {
      setEstimatedSeconds(prev => {
        if (prev === null) return estimatedRemaining
        return prev * 0.7 + estimatedRemaining * 0.3
      })
    }
  }, [progressHistory, progress])

  if (!isOpen || !progress) return null

  const getStatusText = () => {
    switch (progress.status) {
      case 'starting':
        return 'Connecting...'
      case 'syncing':
        return 'Fetching files...'
      case 'parsing':
        return 'Processing documents...'
      case 'embedding':
        return 'Indexing for search...'
      case 'completed':
        return 'All done!'
      case 'error':
        return progress.error || 'Something went wrong'
      default:
        return 'Processing...'
    }
  }

  // Format estimated time
  const getEstimatedTimeText = () => {
    if (estimatedSeconds === null) {
      return 'Estimating...'
    }

    const seconds = Math.round(estimatedSeconds)

    if (seconds < 10) {
      return 'Almost done...'
    } else if (seconds < 60) {
      return `~${seconds}s remaining`
    } else if (seconds < 3600) {
      const mins = Math.ceil(seconds / 60)
      return `~${mins} min remaining`
    } else {
      const hours = Math.round(seconds / 3600 * 10) / 10
      return `~${hours}h remaining`
    }
  }

  const isInProgress = progress.status !== 'completed' && progress.status !== 'error'
  const integrationName = progress.integration.charAt(0).toUpperCase() + progress.integration.slice(1)

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        backdropFilter: 'blur(4px)'
      }}
      onClick={isInProgress ? undefined : onClose}
    >
      <div
        style={{
          backgroundColor: '#FFFBF7',
          borderRadius: '20px',
          padding: '28px',
          maxWidth: '380px',
          width: '90%',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.15)',
          position: 'relative',
          margin: 'auto'
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Close/Minimize Button */}
        {isInProgress && (
          <button
            onClick={onMinimize || onClose}
            style={{
              position: 'absolute',
              top: '16px',
              right: '16px',
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              border: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#9CA3AF',
              transition: 'all 0.2s'
            }}
            onMouseEnter={e => {
              e.currentTarget.style.backgroundColor = '#F3F4F6'
              e.currentTarget.style.color = '#6B7280'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.backgroundColor = 'transparent'
              e.currentTarget.style.color = '#9CA3AF'
            }}
            title="Close - sync will continue in background"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M1 1l12 12M13 1L1 13" />
            </svg>
          </button>
        )}

        {/* Header with Icon */}
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '16px',
              backgroundColor: progress.status === 'completed' ? '#10B981' :
                               progress.status === 'error' ? '#EF4444' : '#F97316',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              boxShadow: '0 4px 12px rgba(249, 115, 22, 0.3)'
            }}
          >
            {progress.status === 'completed' ? (
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : progress.status === 'error' ? (
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            ) : (
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                style={{ animation: 'spin 1s linear infinite' }}
              >
                <path d="M21 12a9 9 0 11-6.219-8.56" />
              </svg>
            )}
          </div>

          <h2 style={{
            fontFamily: '"Work Sans", sans-serif',
            fontSize: '18px',
            fontWeight: 600,
            color: '#18181B',
            margin: '0 0 4px 0'
          }}>
            {progress.status === 'completed' ? 'Sync Complete' :
             progress.status === 'error' ? 'Sync Failed' :
             `Syncing ${integrationName}`}
          </h2>
          <p style={{
            fontFamily: '"Work Sans", sans-serif',
            fontSize: '13px',
            color: '#71717A',
            margin: 0
          }}>
            {getStatusText()}
          </p>
        </div>

        {/* Progress Section */}
        {isInProgress && (
          <>
            {/* Progress Bar */}
            <div style={{ marginBottom: '20px' }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px'
              }}>
                <span style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  color: '#9CA3AF',
                  fontWeight: 500
                }}>
                  {Math.round(progress.progress)}% complete
                </span>
                <span style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  color: '#9CA3AF'
                }}>
                  {getEstimatedTimeText()}
                </span>
              </div>
              <div style={{
                width: '100%',
                height: '6px',
                backgroundColor: '#E5E7EB',
                borderRadius: '3px',
                overflow: 'hidden'
              }}>
                <div
                  style={{
                    width: `${progress.progress}%`,
                    height: '100%',
                    backgroundColor: '#F97316',
                    borderRadius: '3px',
                    transition: 'width 0.5s ease-out'
                  }}
                />
              </div>
            </div>

            {/* Stats Row */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-around',
              padding: '16px 0',
              borderTop: '1px solid #F3F4F6',
              borderBottom: '1px solid #F3F4F6',
              marginBottom: '16px'
            }}>
              <AnimatedCounter value={progress.documentsFound} label="Found" />
              <div style={{ width: '1px', backgroundColor: '#F3F4F6' }} />
              <AnimatedCounter value={progress.documentsParsed} label="Processed" />
              <div style={{ width: '1px', backgroundColor: '#F3F4F6' }} />
              <AnimatedCounter value={progress.documentsEmbedded} label="Indexed" />
            </div>

            {/* Background sync info */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 14px',
              backgroundColor: '#F0FDF4',
              borderRadius: '10px',
              border: '1px solid #BBF7D0'
            }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="7" stroke="#22C55E" strokeWidth="1.5" />
                <path d="M8 5v3M8 10h.01" stroke="#22C55E" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span style={{
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '12px',
                color: '#166534',
                lineHeight: '1.4'
              }}>
                You can close this window. Sync continues in the background.
              </span>
            </div>
          </>
        )}

        {/* Completed State */}
        {progress.status === 'completed' && (
          <>
            <div style={{
              display: 'flex',
              justifyContent: 'space-around',
              padding: '20px 0',
              marginBottom: '20px'
            }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '24px',
                  fontWeight: 600,
                  color: '#10B981'
                }}>
                  {progress.documentsFound}
                </div>
                <div style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  color: '#6B7280'
                }}>
                  documents synced
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '10px',
                border: 'none',
                backgroundColor: '#10B981',
                color: '#fff',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = '#059669'}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = '#10B981'}
            >
              Done
            </button>
          </>
        )}

        {/* Error State */}
        {progress.status === 'error' && (
          <>
            <div style={{
              padding: '16px',
              backgroundColor: '#FEF2F2',
              borderRadius: '10px',
              marginBottom: '20px'
            }}>
              <p style={{
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '13px',
                color: '#991B1B',
                margin: 0,
                lineHeight: '1.5'
              }}>
                {progress.error || 'An unexpected error occurred. Please try again.'}
              </p>
            </div>
            <button
              onClick={onClose}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '10px',
                border: 'none',
                backgroundColor: '#6B7280',
                color: '#fff',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = '#4B5563'}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = '#6B7280'}
            >
              Close
            </button>
          </>
        )}
      </div>

      {/* CSS animation for spinner */}
      <style jsx global>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

// Slack Token Input Modal Component
const SlackTokenModal = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading
}: {
  isOpen: boolean
  onClose: () => void
  onSubmit: (token: string) => void
  isLoading: boolean
}) => {
  const [token, setToken] = useState('')

  if (!isOpen) return null

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#FFF3E4',
          borderRadius: '16px',
          padding: '32px',
          maxWidth: '500px',
          width: '90%'
        }}
        onClick={e => e.stopPropagation()}
      >
        <h2 style={{
          fontFamily: 'Geist, sans-serif',
          fontSize: '20px',
          fontWeight: 600,
          marginBottom: '8px'
        }}>
          Connect Slack
        </h2>

        <p style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '14px',
          color: '#71717A',
          marginBottom: '20px'
        }}>
          Enter your Slack Bot User OAuth Token. You can find this in your Slack App under
          <strong> OAuth & Permissions → Bot User OAuth Token</strong>.
        </p>

        <div style={{ marginBottom: '20px' }}>
          <label style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '14px',
            fontWeight: 500,
            display: 'block',
            marginBottom: '8px'
          }}>
            Bot User OAuth Token
          </label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="xoxb-..."
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '8px',
              border: '1px solid #D4D4D8',
              fontSize: '14px',
              fontFamily: 'monospace'
            }}
          />
        </div>

        <div style={{
          padding: '12px',
          backgroundColor: '#FEF3C7',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <p style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '13px',
            color: '#92400E',
            margin: 0
          }}>
            <strong>Required scopes:</strong> channels:read, channels:history, groups:read, groups:history, users:read, team:read
          </p>
        </div>

        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '12px'
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid #D4D4D8',
              backgroundColor: '#fff',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSubmit(token)}
            disabled={!token.startsWith('xoxb-') || isLoading}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: !token.startsWith('xoxb-') ? '#9ca3af' : '#4A154B',
              color: '#fff',
              fontSize: '14px',
              fontWeight: 500,
              cursor: !token.startsWith('xoxb-') ? 'not-allowed' : 'pointer'
            }}
          >
            {isLoading ? 'Connecting...' : 'Connect'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Integration Details Modal Component
const IntegrationDetailsModal = ({
  isOpen,
  onClose,
  integration,
  onConnect,
  onDisconnect,
  onSync
}: {
  isOpen: boolean
  onClose: () => void
  integration: Integration | null
  onConnect: (id: string) => void
  onDisconnect: (id: string) => void
  onSync: (id: string) => void
}) => {
  if (!isOpen || !integration) return null

  const integrationDetails: Record<string, {
    fullDescription: string
    features: string[]
    dataTypes: string[]
    setupSteps: string[]
    brandColor: string
    docsUrl: string
  }> = {
    slack: {
      fullDescription: 'Slack is a channel-based messaging platform. Connect Slack to automatically import messages, threads, and shared files from your workspace channels into your knowledge base.',
      features: [
        'Import messages from public and private channels',
        'Capture threaded conversations',
        'Index shared files and documents',
        'Real-time sync with configurable intervals'
      ],
      dataTypes: ['Messages', 'Threads', 'Files', 'User mentions'],
      setupSteps: [
        'Enter your Slack Bot User OAuth Token',
        'Select channels to sync',
        'Configure sync frequency',
        'Start initial sync'
      ],
      brandColor: '#4A154B',
      docsUrl: 'https://api.slack.com/docs'
    },
    gmail: {
      fullDescription: 'Gmail integration allows you to import emails and attachments into your knowledge base. Capture important communications, decisions, and documents shared via email.',
      features: [
        'Import emails from specific labels or all mail',
        'Extract and index attachments',
        'Smart filtering by sender or subject',
        'Continuous sync for new emails'
      ],
      dataTypes: ['Emails', 'Attachments', 'Contacts', 'Labels'],
      setupSteps: [
        'Authenticate with Google OAuth',
        'Select labels or folders to sync',
        'Configure filters (optional)',
        'Start synchronization'
      ],
      brandColor: '#EA4335',
      docsUrl: 'https://developers.google.com/gmail/api'
    },
    box: {
      fullDescription: 'Box is a cloud content management platform. Connect Box to import documents, spreadsheets, presentations, and other files stored in your Box folders.',
      features: [
        'Sync files from selected folders',
        'Support for 100+ file types',
        'Automatic parsing and text extraction',
        'Version history tracking'
      ],
      dataTypes: ['Documents', 'Spreadsheets', 'Presentations', 'PDFs', 'Images'],
      setupSteps: [
        'Authenticate with Box OAuth',
        'Select folders to sync',
        'Configure file type filters',
        'Begin document import'
      ],
      brandColor: '#0061D5',
      docsUrl: 'https://developer.box.com/docs'
    },
    github: {
      fullDescription: 'GitHub integration imports code repositories, documentation, issues, and pull requests. Perfect for capturing technical knowledge and development decisions.',
      features: [
        'Import README and documentation files',
        'Index code comments and discussions',
        'Capture issue and PR conversations',
        'Track repository wikis'
      ],
      dataTypes: ['Code', 'Documentation', 'Issues', 'Pull Requests', 'Wikis'],
      setupSteps: [
        'Authenticate with GitHub OAuth',
        'Select repositories to sync',
        'Choose content types to import',
        'Start repository scan'
      ],
      brandColor: '#24292F',
      docsUrl: 'https://docs.github.com/en/rest'
    },
    powerpoint: {
      fullDescription: 'Import Microsoft PowerPoint presentations to capture knowledge from slides, speaker notes, and embedded content. Great for onboarding materials and company presentations.',
      features: [
        'Extract text from all slides',
        'Capture speaker notes',
        'Index embedded images and charts',
        'Maintain slide structure'
      ],
      dataTypes: ['Slides', 'Speaker Notes', 'Images', 'Charts'],
      setupSteps: [
        'Connect Microsoft 365 account',
        'Select OneDrive folders',
        'Choose presentation files',
        'Begin import process'
      ],
      brandColor: '#D24726',
      docsUrl: 'https://docs.microsoft.com/en-us/office/dev/add-ins/'
    },
    excel: {
      fullDescription: 'Microsoft Excel integration imports spreadsheet data, formulas, and structured information. Ideal for capturing data-driven knowledge and business metrics.',
      features: [
        'Import spreadsheet data and tables',
        'Preserve data relationships',
        'Extract charts and visualizations',
        'Support for complex workbooks'
      ],
      dataTypes: ['Spreadsheets', 'Tables', 'Charts', 'Formulas'],
      setupSteps: [
        'Connect Microsoft 365 account',
        'Select OneDrive folders',
        'Choose Excel files',
        'Configure import settings'
      ],
      brandColor: '#217346',
      docsUrl: 'https://docs.microsoft.com/en-us/office/dev/add-ins/'
    },
    pubmed: {
      fullDescription: 'PubMed is a free search engine accessing the MEDLINE database of references and abstracts on life sciences and biomedical topics. Import research papers, citations, and medical literature into your knowledge base.',
      features: [
        'Search 35+ million citations and abstracts',
        'Import full paper metadata and abstracts',
        'Track citation relationships',
        'Access MeSH term classifications'
      ],
      dataTypes: ['Papers', 'Abstracts', 'Citations', 'Authors', 'MeSH Terms'],
      setupSteps: [
        'Connect with NCBI API key (optional)',
        'Configure search queries or topics',
        'Select papers to import',
        'Start literature sync'
      ],
      brandColor: '#326599',
      docsUrl: 'https://pubmed.ncbi.nlm.nih.gov/help/'
    },
    researchgate: {
      fullDescription: 'ResearchGate is a professional network for scientists and researchers. Connect to import publications, access research datasets, and capture insights from the scientific community.',
      features: [
        'Import your publications and papers',
        'Access shared research datasets',
        'Track research metrics and citations',
        'Capture Q&A discussions'
      ],
      dataTypes: ['Publications', 'Datasets', 'Preprints', 'Q&A', 'Profiles'],
      setupSteps: [
        'Authenticate with ResearchGate',
        'Select publications to import',
        'Configure dataset access',
        'Begin research sync'
      ],
      brandColor: '#00D0AF',
      docsUrl: 'https://www.researchgate.net/help'
    },
    googlescholar: {
      fullDescription: 'Google Scholar provides a simple way to broadly search for scholarly literature. Import academic papers, theses, books, and conference papers from across all disciplines.',
      features: [
        'Search across multiple disciplines',
        'Import papers with full citations',
        'Track citation counts and metrics',
        'Access related articles and authors'
      ],
      dataTypes: ['Papers', 'Theses', 'Books', 'Patents', 'Court Opinions'],
      setupSteps: [
        'Configure search preferences',
        'Set up topic alerts',
        'Select papers to import',
        'Enable continuous monitoring'
      ],
      brandColor: '#4285F4',
      docsUrl: 'https://scholar.google.com/intl/en/scholar/help.html'
    }
  }

  const details = integrationDetails[integration.id] || {
    fullDescription: integration.description,
    features: ['Feature details coming soon'],
    dataTypes: ['Various'],
    setupSteps: ['Connect to get started'],
    brandColor: '#6B7280',
    docsUrl: '#'
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#FFF8F0',
          borderRadius: '20px',
          width: '90%',
          maxWidth: '640px',
          maxHeight: '90vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)'
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '24px 32px',
            borderBottom: '1px solid #E5E5E5',
            display: 'flex',
            alignItems: 'center',
            gap: '16px'
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '12px',
              backgroundColor: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid #E5E5E5'
            }}
          >
            <Image
              src={integration.logo}
              alt={integration.name}
              width={36}
              height={36}
              style={{ objectFit: 'contain' }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <h2 style={{
              fontFamily: 'Geist, sans-serif',
              fontSize: '24px',
              fontWeight: 600,
              color: '#18181B',
              margin: 0
            }}>
              {integration.name}
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: '100px',
                  backgroundColor: integration.connected ? '#D1FAE5' : '#F3F4F6',
                  color: integration.connected ? '#059669' : '#6B7280',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '12px',
                  fontWeight: 500
                }}
              >
                {integration.connected ? '● Connected' : '○ Not Connected'}
              </span>
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: '100px',
                  backgroundColor: '#F3F4F6',
                  color: '#6B7280',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '12px',
                  fontWeight: 500
                }}
              >
                {integration.category}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: '#F3F4F6',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6B7280" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '24px 32px', overflowY: 'auto', flex: 1 }}>
          {/* Description */}
          <div style={{ marginBottom: '24px' }}>
            <p style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '15px',
              color: '#52525B',
              lineHeight: '1.6',
              margin: 0
            }}>
              {details.fullDescription}
            </p>
          </div>

          {/* Features */}
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{
              fontFamily: 'Geist, sans-serif',
              fontSize: '14px',
              fontWeight: 600,
              color: '#18181B',
              marginBottom: '12px',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              Features
            </h3>
            <div style={{
              backgroundColor: '#fff',
              borderRadius: '12px',
              border: '1px solid #E5E5E5',
              overflow: 'hidden'
            }}>
              {details.features.map((feature, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '12px 16px',
                    borderBottom: idx < details.features.length - 1 ? '1px solid #F3F4F6' : 'none',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}
                >
                  <div style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    backgroundColor: details.brandColor + '15',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={details.brandColor} strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <span style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    color: '#3F3F46'
                  }}>
                    {feature}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Data Types */}
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{
              fontFamily: 'Geist, sans-serif',
              fontSize: '14px',
              fontWeight: 600,
              color: '#18181B',
              marginBottom: '12px',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              Supported Data Types
            </h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {details.dataTypes.map((type, idx) => (
                <span
                  key={idx}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '8px',
                    backgroundColor: '#fff',
                    border: '1px solid #E5E5E5',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '13px',
                    color: '#52525B'
                  }}
                >
                  {type}
                </span>
              ))}
            </div>
          </div>

          {/* Setup Steps */}
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{
              fontFamily: 'Geist, sans-serif',
              fontSize: '14px',
              fontWeight: 600,
              color: '#18181B',
              marginBottom: '12px',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              Setup Steps
            </h3>
            <div style={{
              backgroundColor: '#fff',
              borderRadius: '12px',
              border: '1px solid #E5E5E5',
              padding: '16px'
            }}>
              {details.setupSteps.map((step, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    marginBottom: idx < details.setupSteps.length - 1 ? '12px' : 0
                  }}
                >
                  <div style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    backgroundColor: details.brandColor,
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '12px',
                    fontWeight: 600,
                    flexShrink: 0
                  }}>
                    {idx + 1}
                  </div>
                  <span style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    color: '#3F3F46',
                    paddingTop: '2px'
                  }}>
                    {step}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Documentation Link */}
          <a
            href={details.docsUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'Inter, sans-serif',
              fontSize: '14px',
              color: details.brandColor,
              textDecoration: 'none'
            }}
          >
            View Documentation
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        </div>

        {/* Footer Actions */}
        <div
          style={{
            padding: '20px 32px',
            borderTop: '1px solid #E5E5E5',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '12px',
            backgroundColor: '#FAFAFA'
          }}
        >
          {integration.connected ? (
            <>
              <button
                onClick={() => onDisconnect(integration.id)}
                style={{
                  padding: '10px 20px',
                  borderRadius: '10px',
                  border: '1px solid #E5E5E5',
                  backgroundColor: '#fff',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#DC2626',
                  cursor: 'pointer'
                }}
              >
                Disconnect
              </button>
              <button
                onClick={() => {
                  onSync(integration.id)
                  onClose()
                }}
                style={{
                  padding: '10px 20px',
                  borderRadius: '10px',
                  border: 'none',
                  backgroundColor: details.brandColor,
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#fff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 11-6.219-8.56" />
                </svg>
                Sync Now
              </button>
            </>
          ) : (
            <button
              onClick={() => {
                onConnect(integration.id)
                onClose()
              }}
              style={{
                padding: '10px 24px',
                borderRadius: '10px',
                border: 'none',
                backgroundColor: details.brandColor,
                fontFamily: 'Inter, sans-serif',
                fontSize: '14px',
                fontWeight: 500,
                color: '#fff',
                cursor: 'pointer'
              }}
            >
              Connect {integration.name}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

const integrations: Integration[] = [
  {
    id: 'slack',
    name: 'Slack',
    logo: '/slack.png',
    description: 'Sync messages from all your Slack channels into your knowledge base.',
    category: 'Conversations',
    connected: false,
    isOAuth: true  // Use OAuth flow like Gmail and Box
  },
  {
    id: 'gmail',
    name: 'Gmail',
    logo: '/gmail.png',
    description: 'Connect your Gmail to import emails into your knowledge base.',
    category: 'Conversations',
    connected: false,
    isOAuth: true
  },
  {
    id: 'box',
    name: 'Box',
    logo: '/box.png',
    description: 'Connect Box to import documents, files, and folders into your knowledge base.',
    category: 'Documents & Recordings',
    connected: false,
    isOAuth: true
  },
  {
    id: 'github',
    name: 'Github',
    logo: '/github.png',
    description: 'Connect GitHub to import repositories, issues, PRs, and documentation into your knowledge base.',
    category: 'Coding',
    connected: false,
    isOAuth: true
  },
  {
    id: 'onedrive',
    name: 'Microsoft 365',
    logo: '/onedrive.png',
    description: 'Connect OneDrive to import PowerPoint, Excel, Word, and PDF files into your knowledge base.',
    category: 'Documents & Recordings',
    connected: false,
    isOAuth: true
  },
  {
    id: 'pubmed',
    name: 'PubMed',
    logo: '/pubmed.png',
    description: 'Access millions of biomedical literature citations and abstracts from MEDLINE.',
    category: 'Research',
    connected: false
  },
  {
    id: 'researchgate',
    name: 'ResearchGate',
    logo: '/researchgate.png',
    description: 'Connect with researchers and access scientific publications and datasets.',
    category: 'Research',
    connected: false
  },
  {
    id: 'googlescholar',
    name: 'Google Scholar',
    logo: '/googlescholar.png',
    description: 'Search scholarly literature across disciplines and sources worldwide.',
    category: 'Research',
    connected: false
  }
]

const IntegrationCard = ({
  integration,
  onToggleConnect,
  onViewDetails,
  onSync,
  isSyncing,
  syncingIntegration
}: {
  integration: Integration;
  onToggleConnect: (id: string) => void;
  onViewDetails: (integration: Integration) => void;
  onSync?: (id: string) => void;
  isSyncing?: boolean;
  syncingIntegration?: string;
}) => {
  const isThisSyncing = syncingIntegration === integration.id;

  return (
    <div
      className={`flex flex-col items-start gap-2 ${
        integration.connected ? 'bg-[#FFE2BF]' : 'bg-secondary'
      }`}
      style={{
        width: '100%',
        padding: '32px',
        borderRight: '1px solid #D4D4D8',
        borderBottom: '1px solid #D4D4D8',
        margin: 0,
        boxSizing: 'border-box'
      }}
    >
      {/* Logo */}
      <div style={{ width: '40px', height: '37px', aspectRatio: '40/37' }}>
        <Image
          src={integration.logo}
          alt={integration.name}
          width={40}
          height={37}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </div>

      {/* Name */}
      <h3
        style={{
          color: '#18181B',
          fontFamily: 'Geist, sans-serif',
          fontSize: '18px',
          fontWeight: 500,
          marginTop: '8px'
        }}
      >
        {integration.name}
      </h3>

      {/* Description - 2 lines */}
      <p
        style={{
          width: '264px',
          color: '#71717A',
          fontFamily: 'Inter, sans-serif',
          fontSize: '14px',
          fontWeight: 400,
          lineHeight: '20px',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden'
        }}
      >
        {integration.description}
      </p>

      {/* Buttons */}
      <div className="flex items-center gap-2 mt-4">
        <button
          onClick={() => !isSyncing && onToggleConnect(integration.id)}
          className={`flex items-center justify-center gap-[4px]`}
          style={{
            padding: '6px 10px',
            borderRadius: '375px',
            border: '0.75px solid #D4D4D8',
            backgroundColor: isSyncing ? '#F59E0B' : integration.connected ? '#000000' : '#FFF3E4',
            boxShadow: '0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 9px 28px 8px rgba(0, 0, 0, 0.05)',
            cursor: isSyncing ? 'default' : 'pointer',
            opacity: isSyncing ? 0.9 : 1,
            flexShrink: 0
          }}
        >
          {isSyncing && (
            <div
              style={{
                width: '12px',
                height: '12px',
                border: '2px solid transparent',
                borderTopColor: '#FFFFFF',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite'
              }}
            />
          )}
          <span
            style={{
              color: isSyncing ? '#FFFFFF' : integration.connected ? '#FFFFFF' : '#1E293B',
              fontFamily: 'Inter, sans-serif',
              fontSize: '12px',
              fontWeight: 400
            }}
          >
            {isSyncing ? 'Connecting' : integration.connected ? 'Connected' : 'Connect'}
          </span>
          {integration.connected && !isSyncing && (
            <div
              style={{
                width: '16px',
                height: '16px',
                borderRadius: '50%',
                backgroundColor: '#10B981',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <span style={{ color: 'white', fontSize: '10px' }}>✓</span>
            </div>
          )}
        </button>

        {/* Sync button - shown when connected and is OAuth */}
        {integration.connected && integration.isOAuth && onSync && (
          <button
            onClick={() => !isThisSyncing && onSync(integration.id)}
            className="flex items-center justify-center gap-[4px]"
            disabled={isThisSyncing}
            style={{
              padding: '6px 10px',
              borderRadius: '375px',
              border: 'none',
              backgroundColor: isThisSyncing ? '#D97706' : '#F59E0B',
              cursor: isThisSyncing ? 'default' : 'pointer',
              opacity: isThisSyncing ? 0.8 : 1,
              transition: 'all 0.2s ease',
              flexShrink: 0
            }}
          >
            {isThisSyncing ? (
              <div
                style={{
                  width: '12px',
                  height: '12px',
                  border: '2px solid transparent',
                  borderTopColor: '#FFFFFF',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite'
                }}
              />
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2"
              >
                <path d="M21 12a9 9 0 11-6.219-8.56" />
              </svg>
            )}
            <span
              style={{
                color: '#FFFFFF',
                fontFamily: 'Inter, sans-serif',
                fontSize: '12px',
                fontWeight: 400
              }}
            >
              {isThisSyncing ? 'Syncing...' : 'Sync'}
            </span>
          </button>
        )}

        <button
          onClick={() => onViewDetails(integration)}
          className="flex items-center gap-1 hover:opacity-70 transition-opacity"
          style={{
            color: '#1E293B',
            fontFamily: 'Inter, sans-serif',
            fontSize: '12px',
            fontWeight: 400,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            whiteSpace: 'nowrap',
            flexShrink: 0
          }}
        >
          Integration details
          <span>→</span>
        </button>
      </div>
    </div>
  )
}

export default function Integrations() {
  const [activeItem, setActiveItem] = useState('Integrations')
  const [activeTab, setActiveTab] = useState('All Integrations')
  // Initialize without localStorage to avoid hydration mismatch
  const [integrationsState, setIntegrationsState] = useState(() =>
    integrations.map(int => ({
      ...int,
      connected: false
    }))
  )
  const [isHydrated, setIsHydrated] = useState(false)
  const [isConnecting, setIsConnecting] = useState<string | null>(null)
  const [syncStatus, setSyncStatus] = useState<string | null>(null)

  // Channel selection state
  const [showChannelModal, setShowChannelModal] = useState(false)
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([])
  const [loadingChannels, setLoadingChannels] = useState(false)

  // Slack token modal state
  const [showSlackTokenModal, setShowSlackTokenModal] = useState(false)
  const [isSubmittingToken, setIsSubmittingToken] = useState(false)

  // Sync progress state
  const [showSyncProgress, setShowSyncProgress] = useState(false)
  const [syncProgress, setSyncProgress] = useState<SyncProgress | null>(null)
  const [syncPollingInterval, setSyncPollingInterval] = useState<NodeJS.Timeout | null>(null)

  // Integration details modal state
  const [showDetailsModal, setShowDetailsModal] = useState(false)
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null)

  // Load localStorage state after hydration to avoid mismatch
  useEffect(() => {
    setIsHydrated(true)
    const savedConnected = loadConnectedIntegrations()
    if (savedConnected.length > 0) {
      setIntegrationsState(prev => prev.map(int => ({
        ...int,
        connected: savedConnected.includes(int.id)
      })))
    }
  }, [])

  // Save connected integrations to localStorage whenever they change (only after hydration)
  useEffect(() => {
    if (!isHydrated) return
    const connectedIds = integrationsState.filter(int => int.connected).map(int => int.id)
    saveConnectedIntegrations(connectedIds)
  }, [integrationsState, isHydrated])

  const categories = ['All Integrations', 'Conversations', 'Coding', 'Documents & Recordings', 'Research']

  // Get auth token for API calls
  const getAuthToken = () => {
    return localStorage.getItem('authToken')
  }

  // Check for existing sync state on mount (resume sync progress if user closed tab)
  useEffect(() => {
    const savedState = loadSyncState()
    if (savedState) {
      // If saved state already shows completed, just restore it without polling
      if (savedState.status === 'completed' || savedState.status === 'error') {
        setSyncProgress({
          integration: savedState.integration,
          status: savedState.status as any,
          progress: savedState.progress || 100,
          documentsFound: savedState.documentsFound || 0,
          documentsParsed: savedState.documentsParsed || 0,
          documentsEmbedded: savedState.documentsEmbedded || 0
        })
        // Don't show modal automatically for old completed syncs
        return
      }

      // There was an active sync - check its status
      const token = getAuthToken()
      if (token) {
        // Poll for current status
        axios.get(`${API_BASE}/integrations/${savedState.integration}/sync/status`, {
          headers: { Authorization: `Bearer ${token}` }
        }).then(response => {
          if (response.data.success) {
            const status = response.data.status
            if (status.status === 'syncing' || status.status === 'parsing' || status.status === 'embedding' || status.status === 'starting') {
              // Sync is still in progress - show the modal and start polling
              setSyncProgress({
                integration: savedState.integration,
                status: status.status,
                progress: status.progress || 0,
                documentsFound: status.documents_found || 0,
                documentsParsed: status.documents_parsed || 0,
                documentsEmbedded: status.documents_embedded || 0,
                currentFile: status.current_file,
                startTime: savedState.startTime
              })
              setShowSyncProgress(true)
              // Start polling
              const interval = setInterval(() => pollSyncStatus(savedState.integration), 1000)
              setSyncPollingInterval(interval)
            } else if (status.status === 'completed') {
              // Sync completed while user was away - keep the completed state
              const integrationName = savedState.integration.charAt(0).toUpperCase() + savedState.integration.slice(1)

              // Mark integration as connected
              setIntegrationsState(prev =>
                prev.map(int =>
                  int.id === savedState.integration ? { ...int, connected: true } : int
                )
              )

              // Show and save completed state
              setSyncProgress({
                integration: savedState.integration,
                status: 'completed',
                progress: 100,
                documentsFound: status.documents_found || 0,
                documentsParsed: status.documents_parsed || 0,
                documentsEmbedded: status.documents_embedded || 0
              })
              setShowSyncProgress(true)
              setSyncStatus(`${integrationName} sync completed while you were away!`)

              // Save completed state so it persists
              saveSyncState({
                integration: savedState.integration,
                status: 'completed',
                progress: 100,
                documentsFound: status.documents_found || 0,
                documentsParsed: status.documents_parsed || 0,
                documentsEmbedded: status.documents_embedded || 0,
                completedAt: Date.now()
              })
            } else {
              // Sync errored or unknown state - clear saved state
              saveSyncState(null)
            }
          }
        }).catch(() => {
          // Error checking status - clear saved state
          saveSyncState(null)
        })
      }
    }
  }, [])

  // Check integration statuses on mount
  useEffect(() => {
    checkIntegrationStatuses()

    // Check URL params for OAuth callback results
    const urlParams = new URLSearchParams(window.location.search)
    const success = urlParams.get('success')
    const error = urlParams.get('error')

    if (success === 'slack') {
      setSyncStatus('Slack connected! Select which channels to sync.')
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === 'slack' ? { ...int, connected: true } : int
        )
      )
      // Clean URL and open channel selection modal
      window.history.replaceState({}, '', '/integrations')
      // Fetch channels and show modal
      fetchSlackChannels()
    } else if (success === 'gmail') {
      setSyncStatus('Gmail connected successfully! You can now sync your emails.')
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === 'gmail' ? { ...int, connected: true } : int
        )
      )
      window.history.replaceState({}, '', '/integrations')
    } else if (success === 'box') {
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === 'box' ? { ...int, connected: true } : int
        )
      )
      window.history.replaceState({}, '', '/integrations')
      // Auto-start sync with progress for Box
      setTimeout(() => startSyncWithProgress('box'), 500)
    } else if (success === 'github') {
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === 'github' ? { ...int, connected: true } : int
        )
      )
      window.history.replaceState({}, '', '/integrations')
      // Auto-start sync with progress for GitHub
      setTimeout(() => startSyncWithProgress('github'), 500)
    } else if (success === 'onedrive') {
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === 'onedrive' ? { ...int, connected: true } : int
        )
      )
      window.history.replaceState({}, '', '/integrations')
      // Auto-start sync with progress for OneDrive
      setTimeout(() => startSyncWithProgress('onedrive'), 500)
    } else if (error) {
      setSyncStatus(`Connection failed: ${error}`)
      window.history.replaceState({}, '', '/integrations')
    }

    // Listen for OAuth callback messages (for popup flow)
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'OAUTH_CONNECTED') {
        const integrationId = event.data.integration
        if (event.data.success) {
          setIntegrationsState(prev =>
            prev.map(int =>
              int.id === integrationId ? { ...int, connected: true } : int
            )
          )
          setSyncStatus(`${integrationId.charAt(0).toUpperCase() + integrationId.slice(1)} connected! You can now sync your data.`)
        } else {
          setSyncStatus(`Connection failed: ${event.data.error}`)
        }
        setIsConnecting(null)
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  const checkIntegrationStatuses = async () => {
    const token = getAuthToken()
    if (!token) return

    try {
      const response = await axios.get(`${API_BASE}/integrations`, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success) {
        const apiIntegrations = response.data.integrations
        setIntegrationsState(prev =>
          prev.map(int => {
            const apiInt = apiIntegrations.find((a: any) => a.type === int.id)
            if (apiInt) {
              return { ...int, connected: apiInt.status === 'connected' }
            }
            return int
          })
        )
      }
    } catch (error) {
      console.error('Error checking integration statuses:', error)
    }
  }

  // Generic OAuth connect function
  const connectOAuth = async (integrationId: string) => {
    setIsConnecting(integrationId)
    setSyncStatus(null)

    const token = getAuthToken()
    if (!token) {
      setSyncStatus('Please log in first')
      setIsConnecting(null)
      return
    }

    try {
      // Get auth URL from backend
      const response = await axios.get(`${API_BASE}/integrations/${integrationId}/auth`, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success && response.data.auth_url) {
        // Redirect to OAuth (Slack requires full page redirect, not popup)
        window.location.href = response.data.auth_url
      } else {
        setSyncStatus(`Error: ${response.data.error || 'Failed to get authorization URL'}`)
        setIsConnecting(null)
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message
      setSyncStatus(`Connection error: ${errorMsg}`)
      setIsConnecting(null)
    }
  }

  // Generic disconnect function
  const disconnectIntegration = async (integrationId: string) => {
    const token = getAuthToken()
    if (!token) return

    try {
      await axios.post(`${API_BASE}/integrations/${integrationId}/disconnect`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setIntegrationsState(prev =>
        prev.map(int =>
          int.id === integrationId ? { ...int, connected: false } : int
        )
      )
      setSyncStatus(`${integrationId.charAt(0).toUpperCase() + integrationId.slice(1)} disconnected.`)
    } catch (error) {
      console.error(`Error disconnecting ${integrationId}:`, error)
    }
  }

  // Fetch Slack channels for selection
  const fetchSlackChannels = async () => {
    const token = getAuthToken()
    if (!token) return

    setLoadingChannels(true)
    try {
      const response = await axios.get(`${API_BASE}/integrations/slack/channels`, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success) {
        setSlackChannels(response.data.channels)
        setShowChannelModal(true)
      } else {
        setSyncStatus(`Error fetching channels: ${response.data.error}`)
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message
      setSyncStatus(`Error fetching channels: ${errorMsg}`)
    } finally {
      setLoadingChannels(false)
    }
  }

  // Save selected Slack channels and start sync
  const saveSlackChannels = async (channelIds: string[]) => {
    const token = getAuthToken()
    if (!token) return

    try {
      // Save channel selection
      await axios.put(`${API_BASE}/integrations/slack/channels`,
        { channels: channelIds },
        { headers: { Authorization: `Bearer ${token}` } }
      )

      setShowChannelModal(false)
      setSyncStatus(`Saved ${channelIds.length} channels. Starting sync...`)

      // Start sync
      await syncIntegration('slack')
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message
      setSyncStatus(`Error saving channels: ${errorMsg}`)
    }
  }

  // Poll for sync status
  const pollSyncStatus = async (integrationId: string) => {
    const token = getAuthToken()
    if (!token) return

    try {
      const response = await axios.get(`${API_BASE}/integrations/${integrationId}/sync/status`, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success) {
        const status = response.data.status
        setSyncProgress({
          integration: integrationId,
          status: status.status,
          progress: status.progress || 0,
          documentsFound: status.documents_found || 0,
          documentsParsed: status.documents_parsed || 0,
          documentsEmbedded: status.documents_embedded || 0,
          currentFile: status.current_file,
          error: status.error
        })

        // Stop polling if completed or error, but keep the completed state visible
        if (status.status === 'completed' || status.status === 'error') {
          if (syncPollingInterval) {
            clearInterval(syncPollingInterval)
            setSyncPollingInterval(null)
          }

          // If completed, ensure integration is marked as connected
          if (status.status === 'completed') {
            setIntegrationsState(prev =>
              prev.map(int =>
                int.id === integrationId ? { ...int, connected: true } : int
              )
            )
          }

          // Keep the completed state in localStorage so it persists
          // Only clear when user explicitly closes or starts new sync
          saveSyncState({
            integration: integrationId,
            status: status.status,
            progress: 100,
            documentsFound: status.documents_found || 0,
            documentsParsed: status.documents_parsed || 0,
            documentsEmbedded: status.documents_embedded || 0,
            completedAt: Date.now()
          })
        }
      }
    } catch (error) {
      console.error('Error polling sync status:', error)
    }
  }

  // Start sync with progress tracking
  const startSyncWithProgress = async (integrationId: string) => {
    const token = getAuthToken()
    if (!token) return

    const startTime = Date.now()

    // Save sync state to localStorage so we can resume if user closes tab
    saveSyncState({ integration: integrationId, startTime })

    // Initialize progress modal
    setSyncProgress({
      integration: integrationId,
      status: 'starting',
      progress: 0,
      documentsFound: 0,
      documentsParsed: 0,
      documentsEmbedded: 0,
      startTime
    })
    setShowSyncProgress(true)
    setSyncStatus(null)

    try {
      // Start the sync
      const response = await axios.post(`${API_BASE}/integrations/${integrationId}/sync`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success) {
        // Start polling for status
        const interval = setInterval(() => pollSyncStatus(integrationId), 1000)
        setSyncPollingInterval(interval)
      } else {
        saveSyncState(null) // Clear saved state on error
        setSyncProgress(prev => prev ? {
          ...prev,
          status: 'error',
          error: response.data.error || 'Sync failed'
        } : null)
      }
    } catch (error: any) {
      saveSyncState(null) // Clear saved state on error
      const errorMsg = error.response?.data?.error || error.message
      setSyncProgress(prev => prev ? {
        ...prev,
        status: 'error',
        error: errorMsg
      } : null)
    }
  }

  // Minimize sync progress modal (hide but keep polling - sync continues in background)
  const minimizeSyncProgress = () => {
    setShowSyncProgress(false)
    // Don't clear syncProgress or polling - sync continues in background
    // The backend runs sync in a separate thread, so it will complete even if user navigates away
  }

  // Close sync progress modal (hide modal but keep completed state for persistence)
  const closeSyncProgress = () => {
    setShowSyncProgress(false)
    // Don't clear syncProgress or saved state - keep it for next time modal opens
    // State will only be cleared when a new sync starts
    if (syncPollingInterval) {
      clearInterval(syncPollingInterval)
      setSyncPollingInterval(null)
    }
  }

  // Smart close - minimize if in progress, full close if completed/error
  const handleSyncModalClose = () => {
    if (syncProgress && (syncProgress.status === 'completed' || syncProgress.status === 'error')) {
      closeSyncProgress()
    } else {
      minimizeSyncProgress()
    }
  }

  // Generic sync function (legacy - for sync buttons)
  const syncIntegration = async (integrationId: string) => {
    // Use the new progress-tracking version
    await startSyncWithProgress(integrationId)
  }

  // Handle Slack token submission
  const submitSlackToken = async (token: string) => {
    setIsSubmittingToken(true)
    try {
      const authToken = getAuthToken()
      const response = await axios.post(
        `${API_BASE}/integrations/slack/token`,
        { access_token: token },
        { headers: { Authorization: `Bearer ${authToken}` } }
      )

      if (response.data.success) {
        setShowSlackTokenModal(false)
        setIntegrationsState(prev =>
          prev.map(int =>
            int.id === 'slack' ? { ...int, connected: true } : int
          )
        )
        setSyncStatus('Slack connected! Select channels to sync.')
        // Fetch channels and show modal
        fetchSlackChannels()
      } else {
        setSyncStatus(`Failed to connect: ${response.data.error}`)
      }
    } catch (error: any) {
      setSyncStatus(`Error: ${error.response?.data?.error || error.message}`)
    } finally {
      setIsSubmittingToken(false)
    }
  }

  const toggleConnect = async (id: string) => {
    const integration = integrationsState.find(i => i.id === id)

    // Handle OAuth integrations (Slack, Gmail, Box, etc.)
    if (integration?.isOAuth) {
      if (integration.connected) {
        await disconnectIntegration(id)
      } else {
        await connectOAuth(id)
      }
      return
    }

    // Handle other integrations (placeholder - show coming soon)
    setSyncStatus(`${integration?.name || id} integration coming soon!`)
  }
  
  // Open integration details modal
  const openDetailsModal = (integration: Integration) => {
    setSelectedIntegration(integration)
    setShowDetailsModal(true)
  }

  const getFilteredIntegrations = () => {
    if (activeTab === 'All Integrations') return integrationsState
    return integrationsState.filter(i => i.category === activeTab)
  }

  const filteredIntegrations = getFilteredIntegrations()

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      {/* Sidebar */}
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-8 py-6 bg-primary">
          <div>
            <h1
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '28px',
                fontWeight: 600,
                lineHeight: '32px'
              }}
            >
              Integrations
            </h1>
            <p
              style={{
                color: '#71717A',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '16px',
                fontWeight: 400,
                lineHeight: '24px',
                marginTop: '6px'
              }}
            >
              Select and connect tools you use to integrate with your KnowledgeVault
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="px-8 pb-4 bg-primary">
          <div className="flex items-center gap-2">
            {categories.map(category => (
              <button
                key={category}
                onClick={() => setActiveTab(category)}
                className={`flex items-center gap-2 ${
                  activeTab === category ? 'bg-secondary' : 'hover:bg-secondary'
                }`}
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  transition: 'background-color 0.2s'
                }}
              >
                <span 
                  style={{
                    color: '#18181B',
                    fontFamily: 'Geist, sans-serif',
                    fontSize: '14px',
                    fontWeight: 400
                  }}
                >
                  {category}
                </span>
                {category === 'All Integrations' && (
                  <div
                    style={{
                      display: 'flex',
                      width: '25px',
                      height: '25px',
                      justifyContent: 'center',
                      alignItems: 'center',
                      borderRadius: '500px',
                      backgroundColor: '#FFF',
                      fontSize: '12px',
                      fontWeight: 500
                    }}
                  >
                    9
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Integrations Grid - 3 columns, no gaps */}
        <div className="flex-1 overflow-y-auto px-8 py-6 bg-primary">
          {/* Status Message */}
          {syncStatus && (
            <div
              className="mb-4 p-4 rounded-lg"
              style={{
                maxWidth: '1100px',
                backgroundColor: syncStatus.includes('error') || syncStatus.includes('failed') || syncStatus.includes('Failed')
                  ? '#FEE2E2'
                  : syncStatus.includes('Syncing')
                    ? '#FEF3C7'
                    : '#D1FAE5',
                border: '1px solid',
                borderColor: syncStatus.includes('error') || syncStatus.includes('failed') || syncStatus.includes('Failed')
                  ? '#FCA5A5'
                  : syncStatus.includes('Syncing')
                    ? '#FCD34D'
                    : '#6EE7B7'
              }}
            >
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '14px' }}>
                {syncStatus}
              </p>
            </div>
          )}

          <div
            className="grid grid-cols-3 gap-0"
            style={{
              maxWidth: '1100px',
              border: '1px solid #D4D4D8',
              borderRadius: '12px',
              overflow: 'hidden',
              display: 'grid'
            }}
          >
            {filteredIntegrations.map(integration => (
              <IntegrationCard
                key={integration.id}
                integration={integration}
                onToggleConnect={toggleConnect}
                onViewDetails={openDetailsModal}
                onSync={syncIntegration}
                isSyncing={syncProgress?.integration === integration.id && syncProgress?.status !== 'completed' && syncProgress?.status !== 'error'}
                syncingIntegration={syncProgress?.status === 'syncing' ? syncProgress?.integration : undefined}
              />
            ))}
          </div>

          {/* Terms and Conditions */}
          <div className="mt-12 text-center">
            <a
              href="#"
              style={{
                color: '#71717A',
                fontFamily: 'Inter, sans-serif',
                fontSize: '14px',
                textDecoration: 'underline'
              }}
            >
              Read our terms and Conditions ↗
            </a>
          </div>
        </div>
      </div>

      {/* Slack Token Input Modal */}
      <SlackTokenModal
        isOpen={showSlackTokenModal}
        onClose={() => setShowSlackTokenModal(false)}
        onSubmit={submitSlackToken}
        isLoading={isSubmittingToken}
      />

      {/* Slack Channel Selection Modal */}
      <ChannelSelectionModal
        isOpen={showChannelModal}
        onClose={() => setShowChannelModal(false)}
        channels={slackChannels}
        onSave={saveSlackChannels}
        isLoading={loadingChannels}
      />

      {/* Sync Progress Modal */}
      <SyncProgressModal
        isOpen={showSyncProgress}
        onClose={handleSyncModalClose}
        progress={syncProgress}
        onMinimize={minimizeSyncProgress}
      />

      {/* Integration Details Modal */}
      <IntegrationDetailsModal
        isOpen={showDetailsModal}
        onClose={() => setShowDetailsModal(false)}
        integration={selectedIntegration}
        onConnect={toggleConnect}
        onDisconnect={disconnectIntegration}
        onSync={syncIntegration}
      />
    </div>
  )
}
