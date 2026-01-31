'use client'

import React, { useState, useEffect } from 'react'
import Sidebar from '../shared/Sidebar'
import Image from 'next/image'
import axios from 'axios'
import { useAuth, useAuthHeaders } from '@/contexts/AuthContext'
import { useRouter } from 'next/navigation'
import DocumentViewer from './DocumentViewer'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003') + '/api'

interface Document {
  id: string
  name: string
  created: string
  lastModified: string
  type: string
  description: string
  category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items' | 'Web Scraper'
  selected: boolean
  classification?: string
  source_type?: string
  folder_path?: string
  content?: string
  url?: string
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

// Classification Badge Component
const ClassificationBadge = ({ classification }: { classification?: string }) => {
  const getClassificationStyle = () => {
    switch (classification?.toLowerCase()) {
      case 'work':
        return { bg: '#DBEAFE', text: '#1E40AF', label: 'Work' }
      case 'personal':
        return { bg: '#FCE7F3', text: '#9F1239', label: 'Personal' }
      case 'spam':
        return { bg: '#FEE2E2', text: '#991B1B', label: 'Spam' }
      default:
        return { bg: '#F3F4F6', text: '#4B5563', label: 'Unknown' }
    }
  }

  const style = getClassificationStyle()

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '4px 12px',
        borderRadius: '16px',
        backgroundColor: style.bg,
        color: style.text,
        fontSize: '12px',
        fontWeight: 500,
        fontFamily: '"Work Sans", sans-serif',
        textTransform: 'capitalize'
      }}
    >
      {style.label}
    </span>
  )
}

export default function Documents() {
  const [activeItem, setActiveItem] = useState('Documents')
  const [documents, setDocuments] = useState<Document[]>([])
  const [filteredDocuments, setFilteredDocuments] = useState<Document[]>([])
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [viewingDocument, setViewingDocument] = useState<FullDocument | null>(null)
  const [loadingDocument, setLoadingDocument] = useState(false)
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set())

  const authHeaders = useAuthHeaders()
  const { token } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (token) {
      loadDocuments()
    }
  }, [token])

  useEffect(() => {
    filterDocuments()
  }, [documents, activeCategory, searchQuery])

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

        const docs: Document[] = apiDocs.map((doc: any, index: number) => {
          let category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items' | 'Web Scraper' = 'Other Items'
          const title = doc.title?.toLowerCase() || ''
          const sourceType = doc.source_type?.toLowerCase() || ''
          const classification = doc.classification?.toLowerCase() || ''

          console.log(`Doc ${index}: ${doc.title} | source_type: ${sourceType} | classification: ${classification}`)

          // Web Scraper documents (HIGHEST PRIORITY)
          if (sourceType === 'webscraper' || sourceType === 'webscraper_enhanced' || sourceType?.includes('webscraper')) {
            category = 'Web Scraper'
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
            content: doc.content
          }
        })

        console.log('Category breakdown:')
        console.log('- Web Scraper:', docs.filter(d => d.category === 'Web Scraper').length)
        console.log('- Documents:', docs.filter(d => d.category === 'Documents').length)
        console.log('- Meetings:', docs.filter(d => d.category === 'Meetings').length)
        console.log('- Personal:', docs.filter(d => d.category === 'Personal Items').length)
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
    if (activeCategory !== 'All') {
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

  const toggleSelect = (id: string) => {
    const newSelected = new Set(selectedDocs)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedDocs(newSelected)
  }

  const getCategoryCounts = () => {
    return {
      all: documents.length,
      meetings: documents.filter(d => d.category === 'Meetings').length,
      documents: documents.filter(d => d.category === 'Documents').length,
      personal: documents.filter(d => d.category === 'Personal Items').length,
      other: documents.filter(d => d.category === 'Other Items').length,
      webscraper: documents.filter(d => d.category === 'Web Scraper').length
    }
  }

  const counts = getCategoryCounts()

  const CategoryFilter = ({ name, count, icon, color, active, onClick }: any) => (
    <button
      onClick={onClick}
      style={{
        padding: '12px 20px',
        borderRadius: '12px',
        border: active ? `2px solid ${color}` : '2px solid transparent',
        backgroundColor: active ? `${color}15` : '#FFFFFF',
        color: '#081028',
        fontFamily: '"Work Sans", sans-serif',
        fontSize: '14px',
        fontWeight: active ? 600 : 500,
        cursor: 'pointer',
        transition: 'all 0.2s',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        boxShadow: active ? `0 2px 8px ${color}25` : '0 1px 3px rgba(0,0,0,0.1)'
      }}
    >
      <span style={{ fontSize: '18px' }}>{icon}</span>
      <span>{name}</span>
      <span style={{
        backgroundColor: color,
        color: '#FFFFFF',
        padding: '2px 8px',
        borderRadius: '10px',
        fontSize: '12px',
        fontWeight: 600,
        minWidth: '24px',
        textAlign: 'center'
      }}>
        {count}
      </span>
    </button>
  )

  const DocumentCard = ({ doc }: { doc: Document }) => {
    const isSelected = selectedDocs.has(doc.id)
    const categoryColor = {
      'Meetings': '#CB3CFF',
      'Documents': '#05C168',
      'Personal Items': '#FDB52A',
      'Other Items': '#086CD9',
      'Web Scraper': '#FF6B35'
    }[doc.category] || '#666'

    return (
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '16px',
          padding: '20px',
          border: isSelected ? `2px solid ${categoryColor}` : '2px solid #E5E7EB',
          boxShadow: isSelected ? `0 4px 12px ${categoryColor}25` : '0 2px 8px rgba(0,0,0,0.05)',
          transition: 'all 0.2s',
          cursor: 'pointer',
          position: 'relative'
        }}
        onMouseEnter={(e) => {
          if (!isSelected) {
            e.currentTarget.style.borderColor = categoryColor
            e.currentTarget.style.boxShadow = `0 4px 12px ${categoryColor}15`
          }
        }}
        onMouseLeave={(e) => {
          if (!isSelected) {
            e.currentTarget.style.borderColor = '#E5E7EB'
            e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.05)'
          }
        }}
      >
        {/* Checkbox */}
        <div
          onClick={(e) => {
            e.stopPropagation()
            toggleSelect(doc.id)
          }}
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            width: '20px',
            height: '20px',
            borderRadius: '6px',
            border: `2px solid ${categoryColor}`,
            backgroundColor: isSelected ? categoryColor : '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer'
          }}
        >
          {isSelected && (
            <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
              <path d="M1 5L4.5 8.5L11 1.5" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>

        {/* Category Badge */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          borderRadius: '8px',
          backgroundColor: `${categoryColor}15`,
          marginBottom: '12px'
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: categoryColor
          }} />
          <span style={{
            color: categoryColor,
            fontSize: '12px',
            fontWeight: 600,
            fontFamily: '"Work Sans", sans-serif'
          }}>
            {doc.category}
          </span>
        </div>

        {/* Document Info */}
        <div onClick={() => viewDocument(doc.id)}>
          <h3 style={{
            fontFamily: '"Work Sans", sans-serif',
            fontSize: '16px',
            fontWeight: 600,
            color: '#081028',
            marginBottom: '8px',
            lineHeight: '1.4',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {doc.name}
          </h3>

          <p style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '13px',
            color: '#6B7280',
            marginBottom: '12px',
            lineHeight: '1.5',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {doc.description}
          </p>

          {/* Meta Info */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            fontSize: '12px',
            color: '#9CA3AF',
            fontFamily: 'Inter, sans-serif',
            flexWrap: 'wrap'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span>📅</span>
              <span>{doc.lastModified}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span>📄</span>
              <span>{doc.type}</span>
            </div>
            {doc.url && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span>🔗</span>
                <span style={{
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}>
                  {doc.url}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Classification */}
        {doc.classification && (
          <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #F3F4F6' }}>
            <ClassificationBadge classification={doc.classification} />
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-[#F9FAFB] overflow-hidden">
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="px-8 py-6 bg-white border-b border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h1 style={{
              color: '#081028',
              fontFamily: '"Work Sans", sans-serif',
              fontSize: '28px',
              fontWeight: 700,
              lineHeight: '1.2'
            }}>
              Knowledge Hub
            </h1>

            <div className="flex items-center gap-3">
              <button
                onClick={() => router.push('/integrations')}
                style={{
                  padding: '10px 20px',
                  borderRadius: '10px',
                  backgroundColor: '#081028',
                  color: '#FFFFFF',
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '14px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>⚡</span>
                <span>Find Gaps</span>
              </button>
            </div>
          </div>

          {/* Search Bar */}
          <div style={{
            position: 'relative',
            width: '100%',
            maxWidth: '600px'
          }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search documents..."
              style={{
                width: '100%',
                padding: '12px 16px 12px 44px',
                borderRadius: '12px',
                border: '2px solid #E5E7EB',
                backgroundColor: '#FFFFFF',
                outline: 'none',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                transition: 'border-color 0.2s'
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = '#081028'}
              onBlur={(e) => e.currentTarget.style.borderColor = '#E5E7EB'}
            />
            <svg
              style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)' }}
              width="18"
              height="18"
              viewBox="0 0 18 18"
              fill="none"
            >
              <circle cx="8" cy="8" r="6" stroke="#9CA3AF" strokeWidth="2"/>
              <path d="M12.5 12.5L16 16" stroke="#9CA3AF" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
        </div>

        {/* Category Filters */}
        <div className="px-8 py-4 bg-white border-b border-gray-200" style={{
          overflowX: 'auto',
          whiteSpace: 'nowrap'
        }}>
          <div style={{ display: 'inline-flex', gap: '12px' }}>
            <CategoryFilter
              name="All"
              count={counts.all}
              icon="📚"
              color="#081028"
              active={activeCategory === 'All'}
              onClick={() => setActiveCategory('All')}
            />
            <CategoryFilter
              name="Web Scraper"
              count={counts.webscraper}
              icon="🌐"
              color="#FF6B35"
              active={activeCategory === 'Web Scraper'}
              onClick={() => setActiveCategory('Web Scraper')}
            />
            <CategoryFilter
              name="Documents"
              count={counts.documents}
              icon="📄"
              color="#05C168"
              active={activeCategory === 'Documents'}
              onClick={() => setActiveCategory('Documents')}
            />
            <CategoryFilter
              name="Meetings"
              count={counts.meetings}
              icon="📅"
              color="#CB3CFF"
              active={activeCategory === 'Meetings'}
              onClick={() => setActiveCategory('Meetings')}
            />
            <CategoryFilter
              name="Personal"
              count={counts.personal}
              icon="👤"
              color="#FDB52A"
              active={activeCategory === 'Personal Items'}
              onClick={() => setActiveCategory('Personal Items')}
            />
            <CategoryFilter
              name="Other"
              count={counts.other}
              icon="📦"
              color="#086CD9"
              active={activeCategory === 'Other Items'}
              onClick={() => setActiveCategory('Other Items')}
            />
          </div>
        </div>

        {/* Documents Grid */}
        <div className="flex-1 px-8 py-6 overflow-auto">
          {loading ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '400px',
              gap: '16px'
            }}>
              <div style={{
                width: '48px',
                height: '48px',
                border: '4px solid #E5E7EB',
                borderTop: '4px solid #081028',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite'
              }}>
                <style jsx>{`
                  @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                  }
                `}</style>
              </div>
              <span style={{
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '16px',
                color: '#6B7280',
                fontWeight: 500
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
              height: '400px',
              gap: '16px',
              backgroundColor: '#FFFFFF',
              borderRadius: '16px',
              padding: '40px',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '64px', opacity: 0.5 }}>📭</div>
              <h3 style={{
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '20px',
                fontWeight: 600,
                color: '#081028',
                marginBottom: '8px'
              }}>
                {searchQuery ? 'No documents found' : 'No documents yet'}
              </h3>
              <p style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '14px',
                color: '#6B7280',
                maxWidth: '400px'
              }}>
                {searchQuery
                  ? `No documents match "${searchQuery}". Try a different search term.`
                  : 'Connect your integrations (Gmail, Slack, Box) or use the Web Scraper to start building your knowledge base.'
                }
              </p>
              {!searchQuery && (
                <button
                  onClick={() => router.push('/integrations')}
                  style={{
                    marginTop: '16px',
                    padding: '12px 24px',
                    borderRadius: '10px',
                    backgroundColor: '#081028',
                    color: '#FFFFFF',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '14px',
                    fontWeight: 600
                  }}
                >
                  Go to Integrations
                </button>
              )}
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
              gap: '20px',
              paddingBottom: '20px'
            }}>
              {filteredDocuments.map(doc => (
                <DocumentCard key={doc.id} doc={doc} />
              ))}
            </div>
          )}

          {/* Results Summary */}
          {!loading && filteredDocuments.length > 0 && (
            <div style={{
              marginTop: '24px',
              padding: '16px',
              backgroundColor: '#FFFFFF',
              borderRadius: '12px',
              textAlign: 'center',
              fontFamily: 'Inter, sans-serif',
              fontSize: '14px',
              color: '#6B7280'
            }}>
              Showing {filteredDocuments.length} of {documents.length} documents
              {activeCategory !== 'All' && ` in ${activeCategory}`}
              {searchQuery && ` matching "${searchQuery}"`}
            </div>
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
            backgroundColor: 'rgba(8, 16, 40, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '16px',
              padding: '32px',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.2)'
            }}
          >
            <span
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '16px',
                fontWeight: 600
              }}
            >
              Loading document...
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
