'use client'

import React, { useState, useEffect } from 'react'
import Sidebar from '../shared/Sidebar'
import Image from 'next/image'
import axios from 'axios'
import { useAuth, useAuthHeaders } from '@/contexts/AuthContext'
import { useRouter } from 'next/navigation'
import DocumentViewer from './DocumentViewer'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003') + '/api'

// Notion-style typography
const notionFont = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif'

interface Document {
  id: string
  name: string
  created: string
  lastModified: string
  type: string
  description: string
  category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items' | 'Web Scraper' | 'Code'
  selected: boolean
  classification?: string
  source_type?: string
  folder_path?: string
  content?: string
  url?: string
  summary?: string
  quickSummary?: string
}

interface FullDocument {
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

export default function Documents() {
  const [activeItem, setActiveItem] = useState('Documents')
  const [documents, setDocuments] = useState<Document[]>([])
  const [filteredDocuments, setFilteredDocuments] = useState<Document[]>([])
  const [activeCategory, setActiveCategory] = useState<string>('All Items')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [viewingDocument, setViewingDocument] = useState<FullDocument | null>(null)
  const [loadingDocument, setLoadingDocument] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [displayLimit, setDisplayLimit] = useState(50)

  const authHeaders = useAuthHeaders()
  const { token } = useAuth()
  const router = useRouter()
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (token) {
      loadDocuments()
    }
  }, [token])

  useEffect(() => {
    filterDocuments()
  }, [documents, activeCategory, searchQuery])

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      if (openMenuId) {
        setOpenMenuId(null)
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [openMenuId])

  const loadDocuments = async () => {
    try {
      console.log('Loading documents from API...')
      const response = await axios.get(`${API_BASE}/documents?limit=100`, {
        headers: authHeaders
      })

      console.log('API Response:', response.data)

      if (response.data.success) {
        const apiDocs = response.data.documents
        console.log(`Loaded ${apiDocs.length} documents from API`)

        // Debug: Check first document's fields
        if (apiDocs.length > 0) {
          console.log('First document fields:', Object.keys(apiDocs[0]))
          console.log('First document summary:', apiDocs[0].summary)
          console.log('First document structured_summary:', apiDocs[0].structured_summary)
        }

        const docs: Document[] = apiDocs.map((doc: any, index: number) => {
          let category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items' | 'Web Scraper' | 'Code' = 'Other Items'
          const title = doc.title?.toLowerCase() || ''
          const sourceType = doc.source_type?.toLowerCase() || ''
          const classification = doc.classification?.toLowerCase() || ''
          const folderPath = doc.metadata?.folder_path?.toLowerCase() || ''

          console.log(`Doc ${index}: ${doc.title} | source_type: "${sourceType}" | classification: ${classification}`)

          // Web Scraper documents (HIGHEST PRIORITY - check first)
          if (sourceType === 'webscraper' ||
              sourceType === 'webscraper_enhanced' ||
              sourceType === 'web_scraper' ||
              sourceType?.toLowerCase().includes('webscraper') ||
              sourceType?.toLowerCase().includes('web_scraper')) {
            category = 'Web Scraper'
            console.log(`  -> Categorized as Web Scraper (source_type: ${sourceType})`)
          }
          // Code files
          else if (sourceType?.includes('code') ||
              title.includes('.js') || title.includes('.ts') || title.includes('.py') ||
              title.includes('.jsx') || title.includes('.tsx') || title.includes('.java') ||
              title.includes('.cpp') || title.includes('.c') || title.includes('.go') ||
              title.includes('.rs') || title.includes('.swift') || title.includes('.kt') ||
              folderPath?.includes('src/') || folderPath?.includes('code/') ||
              doc.metadata?.file_type === 'code') {
            category = 'Code'
          }
          // Backend classification
          else if (classification === 'personal' || classification === 'spam') {
            category = 'Personal Items'
          } else if (classification === 'work') {
            if (title.includes('meeting') || title.includes('schedule') ||
                title.includes('agenda') || title.includes('discussion')) {
              category = 'Meetings'
            } else {
              category = 'Documents'
            }
          }
          // Fallback for files
          else if (sourceType === 'box' || sourceType === 'file') {
            category = 'Documents'
          }

          const createdDate = doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Unknown'
          const modifiedDate = doc.source_created_at ? new Date(doc.source_created_at).toLocaleDateString() : createdDate

          // Create quick 3-5 word summary
          let quickSummary = ''

          // Try different sources for summary
          if (doc.summary && doc.summary.trim()) {
            // Take first 5 words from existing summary
            const words = doc.summary.split(' ').filter((w: string) => w.length > 0).slice(0, 5).join(' ')
            quickSummary = words.length > 40 ? words.substring(0, 40) + '...' : words
          } else if (doc.structured_summary?.summary) {
            const words = doc.structured_summary.summary.split(' ').filter((w: string) => w.length > 0).slice(0, 5).join(' ')
            quickSummary = words.length > 40 ? words.substring(0, 40) + '...' : words
          } else if (doc.content && doc.content.trim().length > 0) {
            // Fallback 1: Use first sentence of content
            const firstSentence = doc.content.trim().split(/[.!?]\s/)[0]
            const words = firstSentence.split(' ').filter((w: string) => w.length > 0).slice(0, 6).join(' ')
            quickSummary = words.length > 50 ? words.substring(0, 50) + '...' : words + '...'
          } else if (doc.metadata?.description) {
            // Fallback 2: Use metadata description
            const words = doc.metadata.description.split(' ').filter((w: string) => w.length > 0).slice(0, 5).join(' ')
            quickSummary = words.length > 40 ? words.substring(0, 40) + '...' : words
          } else {
            // Final fallback: extract from title or use type
            quickSummary = `${doc.source_type || 'Document'} from ${sourceType || 'unknown source'}`
          }

          // Debug logging
          if (!quickSummary || quickSummary === 'No preview available') {
            console.log(`[Summary] No summary for: ${doc.title}`, {
              hasSummary: !!doc.summary,
              hasStructuredSummary: !!doc.structured_summary,
              hasContent: !!doc.content,
              contentLength: doc.content?.length || 0
            })
          }

          return {
            id: doc.id || `doc_${index}`,
            name: doc.title || 'Untitled Document',
            created: createdDate,
            lastModified: modifiedDate,
            type: sourceType === 'webscraper' ? 'Web Page' : sourceType === 'email' ? 'Email' : sourceType === 'box' ? 'Box File' : 'Document',
            description: doc.summary || doc.title || 'No description',
            category,
            selected: false,
            classification: doc.classification,
            source_type: doc.source_type,
            url: doc.metadata?.url || doc.metadata?.source_url,
            content: doc.content,
            summary: doc.summary,
            quickSummary
          }
        })

        console.log('Category breakdown:')
        console.log('- Web Scraper:', docs.filter(d => d.category === 'Web Scraper').length)
        console.log('- Documents:', docs.filter(d => d.category === 'Documents').length)
        console.log('- Meetings:', docs.filter(d => d.category === 'Meetings').length)
        console.log('- Personal:', docs.filter(d => d.category === 'Personal Items').length)
        console.log('- Code:', docs.filter(d => d.category === 'Code').length)
        console.log('- Other:', docs.filter(d => d.category === 'Other Items').length)

        setDocuments(docs)
      } else {
        console.log('API returned error:', response.data.error)
        setDocuments([])
      }
    } catch (error) {
      console.error('Error loading documents:', error)
      setDocuments([])
    } finally {
      setLoading(false)
    }
  }

  const filterDocuments = () => {
    let filtered = documents

    // Filter by category
    if (activeCategory !== 'All Items') {
      filtered = filtered.filter(d => d.category === activeCategory)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(d =>
        d.name.toLowerCase().includes(query) ||
        d.description.toLowerCase().includes(query) ||
        d.type.toLowerCase().includes(query)
      )
    }

    setFilteredDocuments(filtered)
  }

  const viewDocument = async (documentId: string) => {
    setLoadingDocument(true)
    try {
      const response = await axios.get(`${API_BASE}/documents/${documentId}`, {
        headers: authHeaders
      })

      if (response.data.success) {
        setViewingDocument(response.data.document)
      } else {
        alert('Failed to load document: ' + (response.data.error || 'Unknown error'))
      }
    } catch (error: any) {
      console.error('Error loading document:', error)
      alert('Failed to load document: ' + (error.message || 'Unknown error'))
    } finally {
      setLoadingDocument(false)
    }
  }

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (!files || files.length === 0) return

    setUploading(true)
    try {
      const formData = new FormData()
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i])
      }

      const response = await axios.post(`${API_BASE}/documents/upload`, formData, {
        headers: {
          ...authHeaders,
          'Content-Type': 'multipart/form-data'
        }
      })

      if (response.data.success) {
        alert(`Successfully uploaded ${files.length} file(s)`)
        loadDocuments() // Reload documents
      } else {
        alert('Upload failed: ' + (response.data.error || 'Unknown error'))
      }
    } catch (error: any) {
      console.error('Error uploading files:', error)
      alert('Upload failed: ' + (error.response?.data?.error || error.message || 'Unknown error'))
    } finally {
      setUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleAddDocuments = () => {
    fileInputRef.current?.click()
  }

  const handleMoveDocument = async (documentId: string, newClassification: string) => {
    try {
      const response = await axios.post(
        `${API_BASE}/documents/${documentId}/reclassify`,
        { classification: newClassification },
        { headers: authHeaders }
      )

      if (response.data.success) {
        // Reload documents to reflect the change
        loadDocuments()
        setOpenMenuId(null)
      } else {
        alert('Failed to move document: ' + (response.data.error || 'Unknown error'))
      }
    } catch (error: any) {
      console.error('Error moving document:', error)
      alert('Failed to move document: ' + (error.response?.data?.error || error.message || 'Unknown error'))
    }
  }

  const handleDeleteDocument = async (documentId: string, documentName: string) => {
    if (!confirm(`Are you sure you want to delete "${documentName}"?`)) {
      return
    }

    try {
      const response = await axios.delete(
        `${API_BASE}/documents/${documentId}`,
        { headers: authHeaders }
      )

      if (response.data.success) {
        // Reload documents to reflect the change
        loadDocuments()
        setOpenMenuId(null)
      } else {
        alert('Failed to delete document: ' + (response.data.error || 'Unknown error'))
      }
    } catch (error: any) {
      console.error('Error deleting document:', error)
      alert('Failed to delete document: ' + (error.response?.data?.error || error.message || 'Unknown error'))
    }
  }

  const getCategoryCounts = () => {
    return {
      all: documents.length,
      meetings: documents.filter(d => d.category === 'Meetings').length,
      documents: documents.filter(d => d.category === 'Documents').length,
      personal: documents.filter(d => d.category === 'Personal Items').length,
      code: documents.filter(d => d.category === 'Code').length,
      other: documents.filter(d => d.category === 'Other Items').length,
      webscraper: documents.filter(d => d.category === 'Web Scraper').length
    }
  }

  const counts = getCategoryCounts()

  // Large category card component (like in the design)
  const CategoryCard = ({
    title,
    count,
    icon,
    bgColor,
    textColor,
    isLarge,
    onClick,
    active
  }: any) => (
    <button
      onClick={onClick}
      style={{
        backgroundColor: bgColor,
        borderRadius: '16px',
        padding: isLarge ? '32px' : '20px',
        border: active ? '2px solid #374151' : '2px solid rgba(55, 65, 81, 0.2)',
        cursor: 'pointer',
        transition: 'all 0.2s',
        textAlign: 'left',
        width: '100%',
        height: '100%',
        minHeight: isLarge ? '160px' : '112px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        boxShadow: active ? '0 4px 12px rgba(0,0,0,0.1)' : 'none'
      }}
      onMouseEnter={(e) => {
        if (!active) {
          e.currentTarget.style.borderColor = 'rgba(55, 65, 81, 0.4)'
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.borderColor = 'rgba(55, 65, 81, 0.2)'
        }
      }}
    >
      <div style={{
        fontSize: isLarge ? '32px' : '24px',
        color: textColor,
        opacity: 0.9
      }}>
        {icon}
      </div>
      <div>
        <div style={{
          fontFamily: notionFont,
          fontSize: isLarge ? '16px' : '14px',
          fontWeight: 500,
          color: textColor,
          opacity: 0.7,
          marginBottom: '4px'
        }}>
          {title}
        </div>
        <div style={{
          fontFamily: notionFont,
          fontSize: isLarge ? '64px' : '48px',
          fontWeight: 700,
          color: textColor,
          lineHeight: '1',
          letterSpacing: '-0.02em'
        }}>
          {count}
        </div>
      </div>
    </button>
  )

  const DocumentListItem = ({ doc }: { doc: Document }) => {
    const isMenuOpen = openMenuId === doc.id

    return (
      <div
        style={{
          position: 'relative',
          width: '100%',
          padding: '16px 20px',
          backgroundColor: '#FFFFFF',
          border: '1.5px solid #D1D5DB',
          borderRadius: '8px',
          marginBottom: '4px',
          display: 'grid',
          gridTemplateColumns: '2fr 1.5fr 120px 140px 100px 40px',
          alignItems: 'center',
          gap: '16px'
        }}
      >
        {/* Title */}
        <button
          onClick={() => viewDocument(doc.id)}
          style={{
            textAlign: 'left',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            overflow: 'hidden'
          }}
        >
          <div style={{
            fontFamily: notionFont,
            fontSize: '15px',
            fontWeight: 500,
            color: '#111827',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {doc.name}
          </div>
        </button>

        {/* Summary */}
        <div style={{
          fontFamily: notionFont,
          fontSize: '13px',
          color: '#9CA3AF',
          fontStyle: 'italic',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        }}>
          {doc.quickSummary || 'No preview'}
        </div>

        {/* Type */}
        <div style={{
          fontFamily: notionFont,
          fontSize: '13px',
          color: '#6B7280',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        }}>
          {doc.type}
        </div>

        {/* Date Created */}
        <div style={{
          fontFamily: notionFont,
          fontSize: '13px',
          color: '#6B7280',
          whiteSpace: 'nowrap'
        }}>
          {doc.created}
        </div>

        {/* Category */}
        <div style={{
          fontFamily: notionFont,
          fontSize: '13px',
          color: '#6B7280',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        }}>
          {doc.category}
        </div>

        {/* Three-dot menu */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={(e) => {
              e.stopPropagation()
              setOpenMenuId(isMenuOpen ? null : doc.id)
            }}
            style={{
              padding: '8px',
              backgroundColor: 'transparent',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="2" fill="#6B7280"/>
              <circle cx="12" cy="5" r="2" fill="#6B7280"/>
              <circle cx="12" cy="19" r="2" fill="#6B7280"/>
            </svg>
          </button>

          {/* Dropdown menu */}
          {isMenuOpen && (
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: '100%',
                marginTop: '4px',
                backgroundColor: '#FFFFFF',
                border: '1.5px solid #D1D5DB',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
                minWidth: '200px',
                zIndex: 1000,
                overflow: 'hidden'
              }}
            >
              {/* Move to submenu - only show for non-web-scraper documents */}
              {doc.category !== 'Web Scraper' && (
                <div style={{
                  padding: '8px 0',
                  borderBottom: '1px solid #E5E7EB'
                }}>
                  <div style={{
                    padding: '8px 16px',
                    fontFamily: notionFont,
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#6B7280',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em'
                  }}>
                    Move to
                  </div>
                  {['Documents', 'Personal Items', 'Code', 'Other Items'].map((category) => (
                    <button
                      key={category}
                      onClick={() => {
                        const classificationMap: any = {
                          'Documents': 'work',
                          'Personal Items': 'personal',
                          'Code': 'work',
                          'Other Items': 'unknown'
                        }
                        handleMoveDocument(doc.id, classificationMap[category])
                      }}
                      style={{
                        width: '100%',
                        padding: '8px 16px',
                        paddingLeft: '32px',
                        textAlign: 'left',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontFamily: notionFont,
                        fontSize: '14px',
                        color: '#374151',
                        transition: 'background-color 0.15s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F9FAFB'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                      {category}
                    </button>
                  ))}
                </div>
              )}

              {/* Other actions */}
              <div style={{ padding: '4px 0' }}>
                <button
                  onClick={() => viewDocument(doc.id)}
                  style={{
                    width: '100%',
                    padding: '8px 16px',
                    textAlign: 'left',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: notionFont,
                    fontSize: '14px',
                    color: '#374151',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    transition: 'background-color 0.15s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F9FAFB'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                  View Details
                </button>

                <button
                  onClick={() => {
                    if (doc.url) {
                      window.open(doc.url, '_blank')
                    }
                    setOpenMenuId(null)
                  }}
                  style={{
                    width: '100%',
                    padding: '8px 16px',
                    textAlign: 'left',
                    background: 'none',
                    border: 'none',
                    cursor: doc.url ? 'pointer' : 'not-allowed',
                    fontFamily: notionFont,
                    fontSize: '14px',
                    color: doc.url ? '#374151' : '#9CA3AF',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    transition: 'background-color 0.15s'
                  }}
                  onMouseEnter={(e) => {
                    if (doc.url) e.currentTarget.style.backgroundColor = '#F9FAFB'
                  }}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  disabled={!doc.url}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                    <polyline points="15 3 21 3 21 9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
                  Open Source
                </button>

                <button
                  onClick={() => handleDeleteDocument(doc.id, doc.name)}
                  style={{
                    width: '100%',
                    padding: '8px 16px',
                    textAlign: 'left',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: notionFont,
                    fontSize: '14px',
                    color: '#DC2626',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    transition: 'background-color 0.15s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#FEF2F2'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                  Delete
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: '#FFE2BF' }}>
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="px-8 py-6" style={{ backgroundColor: '#FFE2BF' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '24px'
          }}>
            <h1 style={{
              fontFamily: notionFont,
              fontSize: '32px',
              fontWeight: 700,
              color: '#111827',
              letterSpacing: '-0.02em'
            }}>
              Knowledge Hub
            </h1>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button
                style={{
                  padding: '10px 20px',
                  borderRadius: '8px',
                  backgroundColor: '#FFFFFF',
                  color: '#374151',
                  border: '1.5px solid #9CA3AF',
                  cursor: 'pointer',
                  fontFamily: notionFont,
                  fontSize: '14px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#6B7280'
                  e.currentTarget.style.backgroundColor = '#F9FAFB'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#9CA3AF'
                  e.currentTarget.style.backgroundColor = '#FFFFFF'
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3"/>
                  <circle cx="6" cy="12" r="3"/>
                  <circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
                Share
              </button>

              <button
                onClick={handleAddDocuments}
                disabled={uploading}
                style={{
                  padding: '10px 20px',
                  borderRadius: '8px',
                  backgroundColor: uploading ? '#F3F4F6' : '#FFFFFF',
                  color: uploading ? '#9CA3AF' : '#374151',
                  border: '1.5px solid #9CA3AF',
                  cursor: uploading ? 'not-allowed' : 'pointer',
                  fontFamily: notionFont,
                  fontSize: '14px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  if (!uploading) {
                    e.currentTarget.style.borderColor = '#6B7280'
                    e.currentTarget.style.backgroundColor = '#F9FAFB'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!uploading) {
                    e.currentTarget.style.borderColor = '#9CA3AF'
                    e.currentTarget.style.backgroundColor = '#FFFFFF'
                  }
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                {uploading ? 'Uploading...' : 'Add Documents'}
              </button>

              <button
                onClick={() => router.push('/knowledge-gaps')}
                style={{
                  padding: '10px 24px',
                  borderRadius: '8px',
                  backgroundColor: '#A67C52',
                  color: '#FFFFFF',
                  border: '1.5px solid #A67C52',
                  cursor: 'pointer',
                  fontFamily: notionFont,
                  fontSize: '14px',
                  fontWeight: 600,
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#8B6341'
                  e.currentTarget.style.borderColor = '#8B6341'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#A67C52'
                  e.currentTarget.style.borderColor = '#A67C52'
                }}
              >
                Save & Find Gaps
              </button>
            </div>
          </div>

          {/* Search Bar */}
          <div style={{
            position: 'relative',
            width: '100%'
          }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  filterDocuments()
                }
              }}
              placeholder="Search documents..."
              style={{
                width: '100%',
                padding: '12px 16px',
                paddingRight: '50px',
                borderRadius: '8px',
                border: '1.5px solid #D1D5DB',
                backgroundColor: '#FFFFFF',
                outline: 'none',
                fontFamily: notionFont,
                fontSize: '15px',
                color: '#111827',
                transition: 'border-color 0.2s'
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = '#9CA3AF'}
              onBlur={(e) => e.currentTarget.style.borderColor = '#D1D5DB'}
            />
            <button
              onClick={filterDocuments}
              style={{
                position: 'absolute',
                right: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                padding: '8px',
                backgroundColor: '#A67C52',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#8B6341'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#A67C52'}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <path d="m21 21-4.35-4.35"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Category Cards Grid */}
        <div className="px-8 pb-6" style={{ backgroundColor: '#FFE2BF' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(200px, 1fr) repeat(3, 1fr)',
            gridTemplateRows: 'auto auto',
            gap: '16px'
          }}>
            {/* All Items - Large, spans 2 rows */}
            <div style={{ gridColumn: '1 / 2', gridRow: '1 / 3' }}>
              <CategoryCard
                title="All Items"
                count={counts.all}
                icon={
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="14" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="3" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
                  </svg>
                }
                bgColor="#A67C52"
                textColor="#FFFFFF"
                isLarge={true}
                active={activeCategory === 'All Items'}
                onClick={() => setActiveCategory('All Items')}
              />
            </div>

            {/* Row 1 - Right side (3 columns) */}
            {/* Documents */}
            <div style={{ gridColumn: '2 / 3', gridRow: '1 / 2' }}>
              <CategoryCard
                title="Documents"
                count={counts.documents}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M14 2V8H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                }
                bgColor="#D1F5E4"
                textColor="#064E3B"
                isLarge={false}
                active={activeCategory === 'Documents'}
                onClick={() => setActiveCategory('Documents')}
              />
            </div>

            {/* Personal Items */}
            <div style={{ gridColumn: '3 / 4', gridRow: '1 / 2' }}>
              <CategoryCard
                title="Personal Items"
                count={counts.personal}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <circle cx="12" cy="7" r="4" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                }
                bgColor="#F5E6D3"
                textColor="#78350F"
                isLarge={false}
                active={activeCategory === 'Personal Items'}
                onClick={() => setActiveCategory('Personal Items')}
              />
            </div>

            {/* Code */}
            <div style={{ gridColumn: '4 / 5', gridRow: '1 / 2' }}>
              <CategoryCard
                title="Code"
                count={counts.code}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M16 18L22 12L16 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M8 6L2 12L8 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                }
                bgColor="#DBEAFE"
                textColor="#1E3A8A"
                isLarge={false}
                active={activeCategory === 'Code'}
                onClick={() => setActiveCategory('Code')}
              />
            </div>

            {/* Row 2 - Right side (3 columns, equal sizes) */}
            {/* Other Items */}
            <div style={{ gridColumn: '2 / 3', gridRow: '2 / 3' }}>
              <CategoryCard
                title="Other Items"
                count={counts.other}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
                    <circle cx="12" cy="6" r="1.5" fill="currentColor"/>
                    <circle cx="12" cy="18" r="1.5" fill="currentColor"/>
                  </svg>
                }
                bgColor="#E5E7EB"
                textColor="#374151"
                isLarge={false}
                active={activeCategory === 'Other Items'}
                onClick={() => setActiveCategory('Other Items')}
              />
            </div>

            {/* Web Scraper */}
            <div style={{ gridColumn: '3 / 4', gridRow: '2 / 3' }}>
              <CategoryCard
                title="Web Scraper"
                count={counts.webscraper}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                }
                bgColor="#FEF3C7"
                textColor="#92400E"
                isLarge={false}
                active={activeCategory === 'Web Scraper'}
                onClick={() => setActiveCategory('Web Scraper')}
              />
            </div>

            {/* Meetings */}
            <div style={{ gridColumn: '4 / 5', gridRow: '2 / 3' }}>
              <CategoryCard
                title="Meetings"
                count={counts.meetings}
                icon={
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <circle cx="9" cy="7" r="4" stroke="currentColor" strokeWidth="2"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                }
                bgColor="#E0E7FF"
                textColor="#3730A3"
                isLarge={false}
                active={activeCategory === 'Meetings'}
                onClick={() => setActiveCategory('Meetings')}
              />
            </div>
          </div>
        </div>

        {/* Documents List */}
        <div className="flex-1 px-8 py-6 overflow-auto" style={{ backgroundColor: '#FFE2BF' }}>
          {loading ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '300px',
              gap: '16px'
            }}>
              <div style={{
                width: '40px',
                height: '40px',
                border: '3px solid #E5E7EB',
                borderTop: '3px solid #A67C52',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }}>
                <style jsx>{`
                  @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                  }
                `}</style>
              </div>
              <span style={{
                fontFamily: notionFont,
                fontSize: '15px',
                color: '#6B7280'
              }}>
                Loading documents...
              </span>
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '300px',
              gap: '16px',
              backgroundColor: '#FFFFFF',
              borderRadius: '12px',
              padding: '48px'
            }}>
              <div style={{ fontSize: '48px', opacity: 0.4 }}>📭</div>
              <h3 style={{
                fontFamily: notionFont,
                fontSize: '18px',
                fontWeight: 600,
                color: '#111827'
              }}>
                {searchQuery ? 'No documents found' : 'No documents yet'}
              </h3>
              <p style={{
                fontFamily: notionFont,
                fontSize: '14px',
                color: '#6B7280',
                textAlign: 'center',
                maxWidth: '400px',
                lineHeight: '1.6'
              }}>
                {searchQuery
                  ? `No documents match "${searchQuery}". Try a different search.`
                  : 'Connect your integrations or use the Web Scraper to start building your knowledge base.'
                }
              </p>
              {!searchQuery && (
                <button
                  onClick={() => router.push('/integrations')}
                  style={{
                    marginTop: '8px',
                    padding: '10px 20px',
                    borderRadius: '8px',
                    backgroundColor: '#A67C52',
                    color: '#FFFFFF',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: notionFont,
                    fontSize: '14px',
                    fontWeight: 600
                  }}
                >
                  Go to Integrations
                </button>
              )}
            </div>
          ) : (
            <>
              <h2 style={{
                fontFamily: notionFont,
                fontSize: '18px',
                fontWeight: 600,
                color: '#111827',
                marginBottom: '16px',
                letterSpacing: '-0.01em'
              }}>
                {activeCategory}
                <span style={{ color: '#9CA3AF', fontWeight: 400, marginLeft: '8px' }}>
                  ({filteredDocuments.length})
                </span>
              </h2>

              {/* Column Headers */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '2fr 1.5fr 120px 140px 100px 40px',
                gap: '16px',
                padding: '12px 20px',
                backgroundColor: '#F9FAFB',
                borderRadius: '8px',
                marginBottom: '8px'
              }}>
                <div style={{
                  fontFamily: notionFont,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#6B7280',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em'
                }}>
                  Title
                </div>
                <div style={{
                  fontFamily: notionFont,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#6B7280',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em'
                }}>
                  Summary
                </div>
                <div style={{
                  fontFamily: notionFont,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#6B7280',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em'
                }}>
                  Type
                </div>
                <div style={{
                  fontFamily: notionFont,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#6B7280',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em'
                }}>
                  Date Created
                </div>
                <div style={{
                  fontFamily: notionFont,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#6B7280',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em'
                }}>
                  Category
                </div>
                <div></div>
              </div>

              <div>
                {filteredDocuments.slice(0, displayLimit).map(doc => (
                  <DocumentListItem key={doc.id} doc={doc} />
                ))}
              </div>
              {filteredDocuments.length > displayLimit && (
                <div style={{
                  marginTop: '24px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px'
                }}>
                  <div style={{
                    fontFamily: notionFont,
                    fontSize: '14px',
                    color: '#6B7280'
                  }}>
                    Showing {displayLimit} of {filteredDocuments.length} documents
                  </div>
                  <button
                    onClick={() => setDisplayLimit(prev => prev + 50)}
                    style={{
                      padding: '12px 24px',
                      borderRadius: '8px',
                      backgroundColor: '#FFFFFF',
                      color: '#374151',
                      border: '1.5px solid #D1D5DB',
                      cursor: 'pointer',
                      fontFamily: notionFont,
                      fontSize: '14px',
                      fontWeight: 500,
                      transition: 'all 0.2s',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = '#F9FAFB'
                      e.currentTarget.style.borderColor = '#9CA3AF'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = '#FFFFFF'
                      e.currentTarget.style.borderColor = '#D1D5DB'
                    }}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="6 9 12 15 18 9"/>
                    </svg>
                    Show More
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Document Viewer Modal */}
      {viewingDocument && (
        <DocumentViewer
          document={viewingDocument}
          onClose={() => setViewingDocument(null)}
        />
      )}

      {/* Loading Indicator for Document */}
      {loadingDocument && (
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
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '12px',
              padding: '32px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
            }}
          >
            <span
              style={{
                fontFamily: notionFont,
                fontSize: '15px',
                fontWeight: 500,
                color: '#111827'
              }}
            >
              Loading document...
            </span>
          </div>
        </div>
      )}

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.xls"
        onChange={handleFileUpload}
        style={{ display: 'none' }}
      />
    </div>
  )
}
