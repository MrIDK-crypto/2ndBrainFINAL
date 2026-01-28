'use client'

import React from 'react'
import Image from 'next/image'

interface DocumentViewerProps {
  document: {
    id: string
    title: string
    content: string
    content_html?: string
    classification?: string
    source_type?: string
    sender?: string
    sender_email?: string
    recipients?: string[]
    source_created_at?: string
    summary?: string
    metadata?: any
  }
  onClose: () => void
}

export default function DocumentViewer({ document, onClose }: DocumentViewerProps) {
  // Handle escape key to close
  React.useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  // Format classification for display
  const getClassificationBadge = () => {
    if (!document.classification) return null

    const colors: Record<string, { bg: string; text: string }> = {
      work: { bg: '#05C168', text: '#FFFFFF' },
      personal: { bg: '#FDB52A', text: '#081028' },
      spam: { bg: '#CB3CFF', text: '#FFFFFF' },
      unknown: { bg: '#7E89AC', text: '#FFFFFF' }
    }

    const color = colors[document.classification] || colors.unknown

    return (
      <span
        style={{
          padding: '4px 12px',
          borderRadius: '12px',
          backgroundColor: color.bg,
          color: color.text,
          fontSize: '12px',
          fontWeight: 600,
          fontFamily: '"Work Sans", sans-serif'
        }}
      >
        {document.classification.toUpperCase()}
      </span>
    )
  }

  // Format date
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'N/A'
    try {
      return new Date(dateStr).toLocaleString()
    } catch {
      return dateStr
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(8, 16, 40, 0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '20px'
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#FFE2BF',
          borderRadius: '12px',
          border: '1px solid #081028',
          boxShadow: '4px 4px 8px rgba(16, 25, 52, 0.40)',
          maxWidth: '900px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '20px 24px',
            borderBottom: '1px solid #081028',
            backgroundColor: '#FFE2BF'
          }}
        >
          <div style={{ flex: 1, paddingRight: '20px' }}>
            <h2
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '20px',
                fontWeight: 600,
                lineHeight: '24px',
                marginBottom: '8px'
              }}
            >
              {document.title || 'Untitled Document'}
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              {getClassificationBadge()}
              <span
                style={{
                  color: '#7E89AC',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  fontWeight: 400
                }}
              >
                {document.source_type?.toUpperCase() || 'DOCUMENT'}
              </span>
              <span
                style={{
                  color: '#7E89AC',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  fontWeight: 400
                }}
              >
                {formatDate(document.source_created_at)}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '4px',
              backgroundColor: '#081028',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}
          >
            <span style={{ color: '#FFE2BF', fontSize: '20px', fontWeight: 600 }}>×</span>
          </button>
        </div>

        {/* Metadata Section */}
        {(document.sender || document.recipients) && (
          <div
            style={{
              padding: '16px 24px',
              borderBottom: '1px solid #081028',
              backgroundColor: '#FFF3E4'
            }}
          >
            {document.sender && (
              <div style={{ marginBottom: '8px' }}>
                <span
                  style={{
                    color: '#081028',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '13px',
                    fontWeight: 600
                  }}
                >
                  From:{' '}
                </span>
                <span
                  style={{
                    color: '#081028',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '13px',
                    fontWeight: 400
                  }}
                >
                  {document.sender} {document.sender_email && `<${document.sender_email}>`}
                </span>
              </div>
            )}
            {document.recipients && document.recipients.length > 0 && (
              <div>
                <span
                  style={{
                    color: '#081028',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '13px',
                    fontWeight: 600
                  }}
                >
                  To:{' '}
                </span>
                <span
                  style={{
                    color: '#081028',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '13px',
                    fontWeight: 400
                  }}
                >
                  {document.recipients.join(', ')}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Summary Section */}
        {document.summary && (
          <div
            style={{
              padding: '16px 24px',
              borderBottom: '1px solid #081028',
              backgroundColor: '#FFE2BF'
            }}
          >
            <h3
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 600,
                marginBottom: '8px'
              }}
            >
              Summary
            </h3>
            <p
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '13px',
                fontWeight: 400,
                lineHeight: '20px',
                fontStyle: 'italic'
              }}
            >
              {document.summary}
            </p>
          </div>
        )}

        {/* Content Section */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px',
            backgroundColor: '#FFFFFF'
          }}
        >
          {document.content_html ? (
            <div
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 400,
                lineHeight: '22px'
              }}
              dangerouslySetInnerHTML={{ __html: document.content_html }}
            />
          ) : (
            <pre
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 400,
                lineHeight: '22px',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0
              }}
            >
              {document.content || 'No content available'}
            </pre>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            padding: '16px 24px',
            borderTop: '1px solid #081028',
            backgroundColor: '#FFE2BF'
          }}
        >
          <button
            onClick={onClose}
            style={{
              display: 'flex',
              padding: '10px 24px',
              justifyContent: 'center',
              alignItems: 'center',
              borderRadius: '4px',
              backgroundColor: '#081028',
              color: '#FFE2BF',
              border: 'none',
              cursor: 'pointer',
              fontFamily: '"Work Sans", sans-serif',
              fontSize: '14px',
              fontWeight: 600
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
