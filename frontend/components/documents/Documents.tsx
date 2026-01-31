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
  category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items'
  selected: boolean
  // Additional fields from API
  classification?: string
  source_type?: string
  folder_path?: string
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
        padding: '2px 8px',
        borderRadius: '12px',
        backgroundColor: style.bg,
        color: style.text,
        fontSize: '11px',
        fontWeight: 500,
        fontFamily: '"Work Sans", sans-serif',
        textTransform: 'capitalize'
      }}
    >
      {style.label}
    </span>
  )
}

// Classification Dropdown Component
const ClassificationDropdown = ({
  docId,
  currentClassification,
  onClassify
}: {
  docId: string
  currentClassification?: string
  onClassify: (docId: string, classification: string) => void
}) => {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div style={{ position: 'relative' }}>
      <div
        onClick={(e) => {
          e.stopPropagation()
          setIsOpen(!isOpen)
        }}
        style={{ cursor: 'pointer' }}
      >
        <ClassificationBadge classification={currentClassification} />
      </div>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            onClick={() => setIsOpen(false)}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 999
            }}
          />

          {/* Dropdown Menu */}
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              marginTop: '4px',
              backgroundColor: '#FFFFFF',
              border: '1px solid #D4D4D8',
              borderRadius: '8px',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              zIndex: 1000,
              minWidth: '120px'
            }}
          >
            {['work', 'personal', 'spam', 'unknown'].map(classification => (
              <div
                key={classification}
                onClick={(e) => {
                  e.stopPropagation()
                  onClassify(docId, classification)
                  setIsOpen(false)
                }}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontFamily: '"Work Sans", sans-serif',
                  textTransform: 'capitalize',
                  backgroundColor: currentClassification?.toLowerCase() === classification ? '#F3F4F6' : 'transparent',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => {
                  if (currentClassification?.toLowerCase() !== classification) {
                    e.currentTarget.style.backgroundColor = '#F9FAFB'
                  }
                }}
                onMouseLeave={(e) => {
                  if (currentClassification?.toLowerCase() !== classification) {
                    e.currentTarget.style.backgroundColor = 'transparent'
                  }
                }}
              >
                {classification}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

const CategoryCard = ({ icon, title, count, active, onClick, color }: any) => (
  <div
    onClick={onClick}
    className={`flex flex-col items-start justify-center gap-1 cursor-pointer transition-all ${
      active ? 'ring-2 ring-[#081028]' : ''
    }`}
    style={{
      width: '243px',
      height: '80px',
      padding: '16px',
      borderRadius: '8px',
      backgroundColor: '#FFE2BF'
    }}
  >
    <div className="flex items-center gap-2 w-full">
      <div
        style={{
          width: '39.816px',
          height: '40px',
          borderRadius: '80px',
          opacity: 0.2,
          backgroundColor: color,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}
      >
        <Image 
          src={icon} 
          alt={title} 
          width={20} 
          height={20}
          style={{ opacity: 1 }}
        />
      </div>
      <div className="flex flex-col">
        <span
          style={{
            color: '#081028',
            fontFamily: '"Work Sans", sans-serif',
            fontSize: '16px',
            fontWeight: 500,
            lineHeight: '18px'
          }}
        >
          {title}
        </span>
        <span
          style={{
            color: '#081028',
            fontFamily: '"Work Sans", sans-serif',
            fontSize: '12px',
            fontWeight: 400,
            lineHeight: '18px'
          }}
        >
          {count.toLocaleString()}
        </span>
      </div>
    </div>
  </div>
)

export default function Documents() {
  const [activeItem, setActiveItem] = useState('Documents')
  const [documents, setDocuments] = useState<Document[]>([])
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [currentPage, setCurrentPage] = useState(1)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [viewingDocument, setViewingDocument] = useState<FullDocument | null>(null)
  const [loadingDocument, setLoadingDocument] = useState(false)
  const [classifying, setClassifying] = useState(false)

  // Add documents modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [uploadMode, setUploadMode] = useState<'file' | 'text' | 'url'>('file')
  const [uploading, setUploading] = useState(false)
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [textClassification, setTextClassification] = useState('unknown')
  const [urlInput, setUrlInput] = useState('')

  // Video generation modal state
  const [showVideoModal, setShowVideoModal] = useState(false)
  const [videoTitle, setVideoTitle] = useState('')
  const [videoDescription, setVideoDescription] = useState('')
  const [generatingVideo, setGeneratingVideo] = useState(false)
  const [videoProgress, setVideoProgress] = useState<{
    status: string
    progress_percent: number
    current_step: string
  } | null>(null)
  const [createdVideoId, setCreatedVideoId] = useState<string | null>(null)

  const authHeaders = useAuthHeaders()
  const { token } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (token) {
      loadDocuments()
    }
  }, [token])

  const loadDocuments = async () => {
    try {
      // Load documents from the backend with auth (reduced from 500 to 50 for performance)
      const response = await axios.get(`${API_BASE}/documents?limit=50`, {
        headers: authHeaders
      })

      if (response.data.success) {
        const apiDocs = response.data.documents

        // Create documents from API response with categorization
        const docs: Document[] = apiDocs.map((doc: any, index: number) => {
          // Determine category based on classification, folder path, and content
          // PRIORITY ORDER: Backend classification > Folder path > Title keywords
          let category: 'Meetings' | 'Documents' | 'Personal Items' | 'Other Items' = 'Other Items'
          const title = doc.title?.toLowerCase() || ''
          const sourceType = doc.source_type?.toLowerCase() || ''
          const classification = doc.classification?.toLowerCase() || ''

          // Get folder path from metadata if available
          const folderPath = (doc.metadata?.folder_path || doc.metadata?.box_folder_path || '').toLowerCase()

          // FIRST PRIORITY: Backend classification (most reliable)
          // If the backend has classified this document, trust that classification
          if (classification === 'personal' || classification === 'spam') {
            category = 'Personal Items'
          } else if (classification === 'work') {
            // Further categorize work items based on title
            if (title.includes('meeting') || title.includes('schedule') ||
                title.includes('agenda') || title.includes('discussion') ||
                title.includes('call') || title.includes('standup')) {
              category = 'Meetings'
            } else {
              category = 'Documents'
            }
          }
          // If classification is 'unknown' or missing, fall through to heuristics below

          // Second priority: Use folder path for categorization (Box folder structure)
          // Only apply if not already categorized by backend classification
          if (category === 'Other Items' && folderPath) {
            if (folderPath.includes('meeting') || folderPath.includes('calendar') ||
                folderPath.includes('schedule') || folderPath.includes('appointment')) {
              category = 'Meetings'
            } else if (folderPath.includes('personal') || folderPath.includes('private') ||
                       folderPath.includes('family') || folderPath.includes('home')) {
              category = 'Personal Items'
            } else if (folderPath.includes('project') || folderPath.includes('work') ||
                       folderPath.includes('client') || folderPath.includes('business') ||
                       folderPath.includes('report') || folderPath.includes('document')) {
              category = 'Documents'
            }
          }

          // Third priority: Fallback to content-based categorization
          // Only apply if still uncategorized
          if (category === 'Other Items') {
            if (title.includes('meeting') || title.includes('schedule') ||
                title.includes('agenda') || title.includes('discussion') ||
                title.includes('call') || title.includes('standup') ||
                title.includes('sync') || title.includes('review')) {
              category = 'Meetings'
            } else if (title.includes('personal') || title.includes('private') ||
                       title.includes('lunch') || title.includes('dinner') ||
                       title.includes('party') || title.includes('vacation') ||
                       title.includes('birthday') || title.includes('family') ||
                       title.includes('recipe') || title.includes('fitness') ||
                       title.includes('health') || title.includes('hobby')) {
              category = 'Personal Items'
            } else if (title.includes('report') || title.includes('analysis') ||
                       title.includes('document') || title.includes('presentation') ||
                       title.includes('agreement') || title.includes('contract') ||
                       title.includes('proposal') || title.includes('spec') ||
                       sourceType === 'file' || sourceType === 'box' ||
                       sourceType === 'webscraper' || sourceType === 'webscraper_enhanced') {
              // Box files, regular files, and webscraper content default to Documents
              category = 'Documents'
            }
          }

          // Final fallback: If source is Box, file, or webscraper, put in Documents (not Personal Items)
          if (category === 'Other Items' && (sourceType === 'box' || sourceType === 'file' || sourceType === 'webscraper' || sourceType === 'webscraper_enhanced')) {
            category = 'Documents'
          }

          // Format dates
          const createdDate = doc.created_at ? new Date(doc.created_at).toISOString().split('T')[0] : '2025-01-15'
          const modifiedDate = doc.source_created_at ? new Date(doc.source_created_at).toISOString().split('T')[0] : createdDate

          return {
            id: doc.id || `doc_${index}`,
            name: doc.title || 'Untitled Document',
            created: createdDate,
            lastModified: modifiedDate,
            type: sourceType === 'file' ? 'File' : sourceType === 'email' ? 'Email' : sourceType === 'box' ? 'Box File' : sourceType || 'Document',
            description: doc.summary || doc.title || 'No description',
            category,
            selected: false,
            classification: doc.classification,
            source_type: doc.source_type,
            folder_path: folderPath
          }
        })

        setDocuments(docs)
      } else {
        setDocuments([])
      }
    } catch (error) {
      console.error('Error loading documents:', error)
      setDocuments([])
    } finally {
      setLoading(false)
    }
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

  const getCategoryCounts = () => {
    return {
      meetings: documents.filter(d => d.category === 'Meetings').length,
      documents: documents.filter(d => d.category === 'Documents').length,
      personal: documents.filter(d => d.category === 'Personal Items').length,
      other: documents.filter(d => d.category === 'Other Items').length
    }
  }

  const getFilteredDocuments = () => {
    if (activeCategory === 'All') return documents
    return documents.filter(d => d.category === activeCategory)
  }

  const getPaginatedDocuments = () => {
    const filtered = getFilteredDocuments()
    const start = (currentPage - 1) * rowsPerPage
    const end = start + rowsPerPage
    return filtered.slice(start, end)
  }

  const toggleDocument = (id: string) => {
    setDocuments(docs => docs.map(d =>
      d.id === id ? { ...d, selected: !d.selected } : d
    ))
  }

  const toggleSelectAll = () => {
    const filteredIds = new Set(getFilteredDocuments().map(d => d.id))
    const allFilteredSelected = getFilteredDocuments().every(d => d.selected)

    setDocuments(docs => docs.map(d =>
      filteredIds.has(d.id) ? { ...d, selected: !allFilteredSelected } : d
    ))
  }

  const isAllSelected = () => {
    const filtered = getFilteredDocuments()
    return filtered.length > 0 && filtered.every(d => d.selected)
  }

  const isSomeSelected = () => {
    const filtered = getFilteredDocuments()
    return filtered.some(d => d.selected) && !filtered.every(d => d.selected)
  }

  const deleteSelected = async () => {
    const selectedDocs = documents.filter(d => d.selected)
    if (selectedDocs.length === 0) return

    // Confirm deletion
    const confirmMessage = `Are you sure you want to permanently delete ${selectedDocs.length} document(s)? This cannot be undone.`
    if (!confirm(confirmMessage)) {
      return
    }

    setDeleting(true)
    try {
      // Permanently delete from backend (hard delete prevents re-sync)
      const docIds = selectedDocs.map(d => d.id).filter(id => !id.startsWith('personal_'))

      if (docIds.length > 0) {
        const response = await axios.post(`${API_BASE}/documents/bulk/delete`, {
          document_ids: docIds,
          hard: true  // Permanently delete and track external_id to prevent re-sync
        }, { headers: authHeaders })

        // Check response success
        if (!response.data.success) {
          throw new Error(response.data.error || 'Delete failed')
        }

        console.log('Delete results:', response.data.results)
      }

      // Reload documents from backend to ensure UI is in sync
      await loadDocuments()
      setCurrentPage(1)
    } catch (error: any) {
      console.error('Error deleting documents:', error)
      const errorMessage = error.response?.data?.error || error.message || 'Unknown error'
      const statusCode = error.response?.status || 'N/A'
      console.error(`Delete failed - Status: ${statusCode}, Error: ${errorMessage}`)

      if (statusCode === 401) {
        alert('Session expired. Please log in again.')
        // Could redirect to login page here
      } else {
        alert(`Failed to delete documents: ${errorMessage}`)
      }
    } finally {
      setDeleting(false)
    }
  }

  // Classify single document
  const classifyDocument = async (docId: string, classification: string) => {
    try {
      const response = await axios.put(
        `${API_BASE}/documents/${docId}/classify`,
        { classification },
        { headers: authHeaders }
      )

      if (response.data.success) {
        // Update local state
        setDocuments(prev =>
          prev.map(doc =>
            doc.id === docId ? { ...doc, classification } : doc
          )
        )
      } else {
        throw new Error(response.data.error || 'Classification failed')
      }
    } catch (error: any) {
      console.error('Error classifying document:', error)
      alert(`Failed to classify document: ${error.response?.data?.error || error.message}`)
    }
  }

  // Bulk classify selected documents
  const bulkClassify = async (classification: string) => {
    const selectedDocs = documents.filter(d => d.selected)
    if (selectedDocs.length === 0) return

    setClassifying(true)
    try {
      const docIds = selectedDocs.map(d => d.id).filter(id => !id.startsWith('personal_'))

      if (docIds.length > 0) {
        const response = await axios.post(
          `${API_BASE}/documents/bulk/classify`,
          {
            document_ids: docIds,
            classification
          },
          { headers: authHeaders }
        )

        if (!response.data.success) {
          throw new Error(response.data.error || 'Bulk classification failed')
        }

        // Update local state for all successfully classified documents
        setDocuments(prev =>
          prev.map(doc =>
            selectedDocs.some(sd => sd.id === doc.id) ? { ...doc, classification } : doc
          )
        )

        console.log(`Successfully classified ${docIds.length} documents as ${classification}`)
      }
    } catch (error: any) {
      console.error('Error bulk classifying:', error)
      alert(`Failed to classify documents: ${error.response?.data?.error || error.message}`)
    } finally {
      setClassifying(false)
    }
  }

  // Handle file upload
  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    setUploading(true)
    try {
      const formData = new FormData()
      Array.from(files).forEach(file => {
        formData.append('files', file)
      })

      const response = await axios.post(
        `${API_BASE}/documents/upload`,
        formData,
        {
          headers: {
            'Authorization': authHeaders.Authorization,
            'X-Tenant': authHeaders['X-Tenant']
            // Let axios set Content-Type automatically with boundary
          }
        }
      )

      if (response.data.success) {
        setShowAddModal(false)
        await loadDocuments()
        alert(`Successfully uploaded ${response.data.count} document(s)!`)
      } else {
        throw new Error(response.data.error || 'Upload failed')
      }
    } catch (error: any) {
      console.error('Error uploading files:', error)
      alert(`Failed to upload files: ${error.response?.data?.error || error.message}`)
    } finally {
      setUploading(false)
    }
  }

  // Handle text paste
  const handleTextPaste = async () => {
    if (!textTitle.trim() || !textContent.trim()) {
      alert('Please provide both title and content')
      return
    }

    if (textContent.length < 50) {
      alert('Content must be at least 50 characters')
      return
    }

    setUploading(true)
    try {
      const response = await axios.post(
        `${API_BASE}/documents/upload`,
        {
          title: textTitle,
          content: textContent,
          classification: textClassification
        },
        { headers: authHeaders }
      )

      if (response.data.success) {
        setShowAddModal(false)
        setTextTitle('')
        setTextContent('')
        setTextClassification('unknown')
        await loadDocuments()
        alert('Document added successfully!')
      } else {
        throw new Error(response.data.error || 'Upload failed')
      }
    } catch (error: any) {
      console.error('Error adding document:', error)
      alert(`Failed to add document: ${error.response?.data?.error || error.message}`)
    } finally {
      setUploading(false)
    }
  }

  const handleUrlAdd = async () => {
    if (!urlInput.trim()) {
      alert('Please provide a URL')
      return
    }

    // Validate URL format
    try {
      new URL(urlInput)
    } catch {
      alert('Please provide a valid URL (e.g., https://example.com)')
      return
    }

    setUploading(true)
    try {
      const response = await axios.post(
        `${API_BASE}/documents/upload-url`,
        {
          url: urlInput,
          classification: textClassification
        },
        { headers: authHeaders }
      )

      if (response.data.success) {
        setShowAddModal(false)
        setUrlInput('')
        setTextClassification('unknown')
        await loadDocuments()
        alert(`Document added successfully! ${response.data.documents?.length || 0} document(s) imported.`)
      } else {
        throw new Error(response.data.error || 'Upload failed')
      }
    } catch (error: any) {
      console.error('Error adding document from URL:', error)
      alert(`Failed to fetch content from URL: ${error.response?.data?.error || error.message}`)
    } finally {
      setUploading(false)
    }
  }

  const saveAndAnalyzeGaps = async () => {
    setSaving(true)
    try {
      // Get count of non-personal documents to analyze
      const docsToAnalyze = documents.filter(d =>
        !d.id.startsWith('personal_') && d.category !== 'Personal Items'
      ).length

      if (docsToAnalyze === 0) {
        alert('No work documents to analyze. Please sync some documents first.')
        setSaving(false)
        return
      }

      // Trigger knowledge gap analysis directly
      // The backend now includes pending documents (include_pending: true by default)
      const response = await axios.post(`${API_BASE}/knowledge/analyze`, {
        force: true,
        include_pending: true  // Explicitly include pending/unclassified docs
      }, { headers: authHeaders })

      if (response.data.success) {
        const gapCount = response.data.results?.gaps?.length || 0
        const docsAnalyzed = response.data.results?.total_documents_analyzed || 0

        if (gapCount > 0) {
          alert(`Analysis complete! Analyzed ${docsAnalyzed} documents and found ${gapCount} knowledge gaps. Redirecting to Knowledge Gaps page...`)
          router.push('/knowledge-gaps')
        } else if (docsAnalyzed === 0) {
          alert('No documents found to analyze. Please make sure you have synced some documents from Box or other sources.')
        } else {
          alert(`Analyzed ${docsAnalyzed} documents but no knowledge gaps were identified. Your documentation may already be comprehensive!`)
          router.push('/knowledge-gaps')
        }
      } else {
        alert('Analysis failed: ' + (response.data.error || 'Unknown error'))
      }
    } catch (error: any) {
      console.error('Error analyzing knowledge gaps:', error)
      const errorMsg = error.response?.data?.error || error.message || 'Unknown error'
      alert(`Failed to analyze knowledge gaps: ${errorMsg}`)
    } finally {
      setSaving(false)
    }
  }

  // Video generation functions
  const handleGenerateVideo = () => {
    const selectedDocs = documents.filter(d => d.selected)
    if (selectedDocs.length === 0) {
      alert('Please select at least one document to generate a video')
      return
    }
    setVideoTitle('')
    setVideoDescription('')
    setShowVideoModal(true)
  }

  const createVideo = async () => {
    if (!videoTitle.trim()) {
      alert('Please enter a video title')
      return
    }

    const selectedDocIds = documents.filter(d => d.selected).map(d => d.id)
    if (selectedDocIds.length === 0) {
      alert('Please select at least one document')
      return
    }

    setGeneratingVideo(true)
    try {
      const response = await axios.post(
        `${API_BASE}/videos`,
        {
          title: videoTitle,
          description: videoDescription || undefined,
          source_type: 'documents',
          source_ids: selectedDocIds
        },
        { headers: authHeaders }
      )

      if (response.data.success) {
        const videoId = response.data.video.id
        setCreatedVideoId(videoId)

        // Start polling for progress
        pollVideoStatus(videoId)
      } else {
        alert('Failed to create video: ' + (response.data.error || 'Unknown error'))
        setGeneratingVideo(false)
      }
    } catch (error: any) {
      console.error('Error creating video:', error)
      alert('Failed to create video: ' + (error.response?.data?.error || error.message))
      setGeneratingVideo(false)
    }
  }

  const pollVideoStatus = async (videoId: string) => {
    try {
      const response = await axios.get(
        `${API_BASE}/videos/${videoId}/status`,
        { headers: authHeaders }
      )

      if (response.data.success) {
        setVideoProgress({
          status: response.data.status,
          progress_percent: response.data.progress_percent || 0,
          current_step: response.data.current_step || 'Processing...'
        })

        if (response.data.status === 'completed') {
          // Video is ready!
          setTimeout(() => {
            setGeneratingVideo(false)
            setShowVideoModal(false)
            setVideoProgress(null)
            setCreatedVideoId(null)
            alert('Video generated successfully! Redirecting to Training Guides...')
            router.push('/training-guides')
          }, 1500)
        } else if (response.data.status === 'failed') {
          setGeneratingVideo(false)
          setVideoProgress(null)
          alert('Video generation failed: ' + (response.data.error_message || 'Unknown error'))
        } else {
          // Still processing, poll again in 3 seconds
          setTimeout(() => pollVideoStatus(videoId), 3000)
        }
      }
    } catch (error: any) {
      console.error('Error polling video status:', error)
      // Retry after 3 seconds
      setTimeout(() => pollVideoStatus(videoId), 3000)
    }
  }

  const hasSelectedDocs = documents.some(d => d.selected)

  const counts = getCategoryCounts()
  const filteredDocs = getFilteredDocuments()
  const paginatedDocs = getPaginatedDocuments()
  const totalPages = Math.ceil(filteredDocs.length / rowsPerPage)

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-8 py-4 bg-primary">
          <h1
            style={{
              color: '#081028',
              fontFamily: '"Work Sans", sans-serif',
              fontSize: '20px',
              fontWeight: 600,
              lineHeight: '22px'
            }}
          >
            Knowledge Hub
          </h1>

          <div className="flex items-center gap-4">
            <input
              type="text"
              placeholder="Search for..."
              style={{
                width: '352px',
                height: '42px',
                padding: '0 16px',
                borderRadius: '4px',
                border: '0.6px solid #7E89AC',
                backgroundColor: '#FFE2BF',
                outline: 'none',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px'
              }}
            />

            <button
              style={{
                display: 'flex',
                width: '137px',
                height: '42px',
                padding: '0 16px',
                justifyContent: 'center',
                alignItems: 'center',
                borderRadius: '4px',
                backgroundColor: '#FFE2BF',
                border: 'none',
                cursor: 'pointer',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 500
              }}
            >
              Share
            </button>

            <button
              onClick={() => setShowAddModal(true)}
              style={{
                display: 'flex',
                width: '137px',
                height: '42px',
                padding: '0 16px',
                justifyContent: 'center',
                alignItems: 'center',
                borderRadius: '4px',
                backgroundColor: '#FFE2BF',
                border: 'none',
                cursor: 'pointer',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 500
              }}
            >
              Add Documents
            </button>

            <button
              onClick={handleGenerateVideo}
              disabled={!hasSelectedDocs}
              style={{
                display: 'flex',
                width: '160px',
                height: '42px',
                padding: '0 16px',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '6px',
                borderRadius: '4px',
                backgroundColor: !hasSelectedDocs ? '#ccc' : '#FF6B35',
                border: 'none',
                cursor: !hasSelectedDocs ? 'not-allowed' : 'pointer',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 500,
                color: '#FFFFFF',
                opacity: !hasSelectedDocs ? 0.6 : 1
              }}
            >
              🎬 Generate Video
            </button>

            <button
              onClick={saveAndAnalyzeGaps}
              disabled={saving || documents.length === 0}
              style={{
                display: 'flex',
                width: '180px',
                height: '42px',
                padding: '0 16px',
                justifyContent: 'center',
                alignItems: 'center',
                borderRadius: '4px',
                backgroundColor: saving ? '#ccc' : '#081028',
                color: '#FFE2BF',
                border: 'none',
                cursor: saving || documents.length === 0 ? 'not-allowed' : 'pointer',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                fontWeight: 600,
                opacity: saving || documents.length === 0 ? 0.6 : 1
              }}
            >
              {saving ? 'Analyzing...' : 'Save & Find Gaps'}
            </button>
          </div>
        </div>

        {/* Category Cards */}
        <div className="px-8 py-4 bg-primary">
          <div style={{ display: 'inline-flex', alignItems: 'flex-start', gap: '30px' }}>
            <CategoryCard
              icon="/meetings.png"
              title="Meetings"
              count={counts.meetings}
              color="#CB3CFF"
              active={activeCategory === 'Meetings'}
              onClick={() => setActiveCategory('Meetings')}
            />
            <CategoryCard
              icon="/docs.png"
              title="Documents"
              count={counts.documents}
              color="#05C168"
              active={activeCategory === 'Documents'}
              onClick={() => setActiveCategory('Documents')}
            />
            <CategoryCard
              icon="/personal.svg"
              title="Personal Items"
              count={counts.personal}
              color="#FDB52A"
              active={activeCategory === 'Personal Items'}
              onClick={() => setActiveCategory('Personal Items')}
            />
            <CategoryCard
              icon="/other.svg"
              title="Other Items"
              count={counts.other}
              color="#086CD9"
              active={activeCategory === 'Other Items'}
              onClick={() => setActiveCategory('Other Items')}
            />
          </div>
        </div>

        {/* Documents Table */}
        <div className="flex-1 px-8 py-4 bg-primary overflow-auto flex items-start">
          <div
            style={{
              width: '1060px',
              minHeight: '400px',
              borderRadius: '12px',
              border: '1px solid #081028',
              backgroundColor: '#FFE2BF',
              boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
              display: 'flex',
              flexDirection: 'column',
              position: 'relative'
            }}
          >
            {/* Action buttons - positioned absolutely */}
            {hasSelectedDocs && (
              <div style={{
                position: 'absolute',
                right: '16px',
                top: '16px',
                display: 'flex',
                gap: '8px',
                zIndex: 10
              }}>
                {/* Bulk Classify Dropdown */}
                <div style={{ position: 'relative' }}>
                  <button
                    disabled={classifying}
                    onMouseEnter={(e) => {
                      const menu = e.currentTarget.nextElementSibling as HTMLElement
                      if (menu) menu.style.display = 'block'
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      color: '#081028',
                      fontFamily: '"Work Sans"',
                      fontSize: '10px',
                      fontWeight: 600,
                      lineHeight: '10px',
                      background: 'none',
                      border: 'none',
                      cursor: classifying ? 'not-allowed' : 'pointer',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: '#FFE2BF',
                      opacity: classifying ? 0.6 : 1
                    }}
                  >
                    {classifying ? 'Classifying...' : 'Classify'}
                  </button>

                  {/* Dropdown Menu */}
                  <div
                    style={{
                      display: 'none',
                      position: 'absolute',
                      top: '100%',
                      right: 0,
                      marginTop: '4px',
                      backgroundColor: '#FFFFFF',
                      border: '1px solid #D4D4D8',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                      zIndex: 1000,
                      minWidth: '120px'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.display = 'block'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                  >
                    {['work', 'personal', 'spam', 'unknown'].map(classification => (
                      <div
                        key={classification}
                        onClick={() => bulkClassify(classification)}
                        style={{
                          padding: '8px 12px',
                          cursor: 'pointer',
                          fontSize: '12px',
                          fontFamily: '"Work Sans", sans-serif',
                          textTransform: 'capitalize',
                          transition: 'background-color 0.15s'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = '#F9FAFB'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = 'transparent'
                        }}
                      >
                        {classification}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Delete Button */}
                <button
                  onClick={deleteSelected}
                  disabled={deleting}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    color: '#081028',
                    fontFamily: '"Work Sans"',
                    fontSize: '10px',
                    fontWeight: 600,
                    lineHeight: '10px',
                    background: 'none',
                    border: 'none',
                    cursor: deleting ? 'not-allowed' : 'pointer',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    backgroundColor: '#FFE2BF',
                    opacity: deleting ? 0.6 : 1
                  }}
                >
                  <div
                    style={{
                      width: '12px',
                      height: '12px',
                      borderRadius: '2px',
                      border: '0.6px solid #CB3CFF',
                      backgroundColor: '#CB3CFF',
                      boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                  >
                    <Image src="/check.svg" alt="checked" width={6} height={5} />
                  </div>
                  {deleting ? 'Deleting...' : 'Delete all'}
                </button>
              </div>
            )}
            
            {/* Table Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '16px',
                borderBottom: '1px solid #000',
                backgroundColor: '#FFE2BF'
              }}
            >
              <div style={{ width: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div
                  onClick={toggleSelectAll}
                  style={{
                    width: '12px',
                    height: '12px',
                    borderRadius: '2px',
                    border: '0.6px solid #CB3CFF',
                    backgroundColor: isAllSelected() ? '#CB3CFF' : 'transparent',
                    boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    position: 'relative'
                  }}
                >
                  {isAllSelected() && (
                    <Image src="/check.svg" alt="checked" width={6} height={5} />
                  )}
                  {isSomeSelected() && !isAllSelected() && (
                    <div style={{
                      width: '6px',
                      height: '2px',
                      backgroundColor: '#CB3CFF',
                      borderRadius: '1px'
                    }} />
                  )}
                </div>
              </div>
              <div style={{ flex: 1, color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Document name
              </div>
              <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Created
              </div>
              <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Last Modified
              </div>
              <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Document Type
              </div>
              <div style={{ width: '120px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Classification
              </div>
              <div style={{ width: '200px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 500 }}>
                Description
              </div>
            </div>

            {/* Table Body */}
            <div style={{ overflowX: 'hidden' }}>
              {loading ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px' }}>
                  <span style={{ fontFamily: '"Work Sans"', fontSize: '14px', color: '#081028' }}>
                    Loading documents...
                  </span>
                </div>
              ) : paginatedDocs.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px' }}>
                  <span style={{ fontFamily: '"Work Sans"', fontSize: '14px', color: '#081028' }}>
                    No documents found. Make sure Flask backend is running.
                  </span>
                </div>
              ) : (
                paginatedDocs.map((doc, index) => (
                  <div
                    key={doc.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '16px',
                      minHeight: '61px',
                      borderBottom: '1px solid #000',
                      backgroundColor: index % 2 === 0 ? '#FFE2BF' : '#FFF3E4'
                    }}
                  >
                    <div style={{ width: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <div
                        onClick={() => toggleDocument(doc.id)}
                        style={{
                          width: '12px',
                          height: '12px',
                          borderRadius: '2px',
                          border: '0.6px solid #CB3CFF',
                          backgroundColor: doc.selected ? '#CB3CFF' : 'transparent',
                          boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                      >
                        {doc.selected && (
                          <Image src="/check.svg" alt="checked" width={6} height={5} />
                        )}
                      </div>
                    </div>
                    <div
                      onClick={() => viewDocument(doc.id)}
                      style={{
                        flex: 1,
                        color: '#081028',
                        fontFamily: '"Work Sans"',
                        fontSize: '13px',
                        fontWeight: 400,
                        lineHeight: '16px',
                        cursor: 'pointer',
                        textDecoration: 'underline'
                      }}
                    >
                      {doc.name}
                    </div>
                    <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 400, lineHeight: '16px' }}>
                      {doc.created}
                    </div>
                    <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 400, lineHeight: '16px' }}>
                      {doc.lastModified}
                    </div>
                    <div style={{ width: '150px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 400, lineHeight: '16px' }}>
                      {doc.type}
                    </div>
                    <div style={{ width: '120px', display: 'flex', alignItems: 'center' }}>
                      <ClassificationDropdown
                        docId={doc.id}
                        currentClassification={doc.classification}
                        onClassify={classifyDocument}
                      />
                    </div>
                    <div style={{ width: '200px', color: '#081028', fontFamily: '"Work Sans"', fontSize: '13px', fontWeight: 400, lineHeight: '16px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.description}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Pagination Footer */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px',
                borderTop: '1px solid #000',
                backgroundColor: '#FFE2BF'
              }}
            >
              <span
                style={{
                  color: '#081028',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '12px',
                  fontWeight: 500,
                  lineHeight: '18px'
                }}
              >
                {((currentPage - 1) * rowsPerPage) + 1} - {Math.min(currentPage * rowsPerPage, filteredDocs.length)} of {filteredDocs.length}
              </span>

              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span
                  style={{
                    color: '#081028',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '12px',
                    fontWeight: 500,
                    lineHeight: '18px'
                  }}
                >
                  Rows per page:
                </span>
                <select
                  value={rowsPerPage}
                  onChange={(e) => setRowsPerPage(Number(e.target.value))}
                  style={{
                    padding: '6px 8px',
                    borderRadius: '4px',
                    border: '0.6px solid #0B1739',
                    backgroundColor: '#FFE2BF',
                    boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={250}>250</option>
                  <option value={500}>500</option>
                  <option value={1000}>All</option>
                </select>

                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  style={{
                    display: 'flex',
                    padding: '6px',
                    borderRadius: '4px',
                    border: '0.6px solid #0B1739',
                    backgroundColor: '#FFE2BF',
                    boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                    cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                    opacity: currentPage === 1 ? 0.5 : 1
                  }}
                >
                  <Image src="/left.svg" alt="Previous" width={16} height={16} />
                </button>

                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  style={{
                    display: 'flex',
                    padding: '6px',
                    borderRadius: '4px',
                    border: '0.6px solid #0B1739',
                    backgroundColor: '#FFE2BF',
                    boxShadow: '1px 1px 1px 0 rgba(16, 25, 52, 0.40)',
                    cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                    opacity: currentPage === totalPages ? 0.5 : 1
                  }}
                >
                  <Image src="/right.svg" alt="Next" width={16} height={16} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Add Documents Modal */}
      {showAddModal && (
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
          onClick={() => setShowAddModal(false)}
        >
          <div
            style={{
              backgroundColor: '#FFF3E4',
              borderRadius: '16px',
              padding: '32px',
              maxWidth: '600px',
              width: '90%',
              maxHeight: '90vh',
              overflow: 'auto'
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{
              fontFamily: '"Work Sans", sans-serif',
              fontSize: '20px',
              fontWeight: 600,
              marginBottom: '8px'
            }}>
              Add Documents
            </h2>

            <p style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '14px',
              color: '#71717A',
              marginBottom: '20px'
            }}>
              Upload files or paste text to add to your knowledge base
            </p>

            {/* Mode Toggle */}
            <div style={{
              display: 'flex',
              gap: '8px',
              marginBottom: '20px',
              borderBottom: '1px solid #D4D4D8',
              paddingBottom: '8px'
            }}>
              <button
                onClick={() => setUploadMode('file')}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: uploadMode === 'file' ? '#081028' : 'transparent',
                  color: uploadMode === 'file' ? '#FFE2BF' : '#081028',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif'
                }}
              >
                Upload Files
              </button>
              <button
                onClick={() => setUploadMode('text')}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: uploadMode === 'text' ? '#081028' : 'transparent',
                  color: uploadMode === 'text' ? '#FFE2BF' : '#081028',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif'
                }}
              >
                Paste Text
              </button>
              <button
                onClick={() => setUploadMode('url')}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: uploadMode === 'url' ? '#081028' : 'transparent',
                  color: uploadMode === 'url' ? '#FFE2BF' : '#081028',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif'
                }}
              >
                Add from URL
              </button>
            </div>

            {/* File Upload Mode */}
            {uploadMode === 'file' && (
              <div>
                <div style={{
                  border: '2px dashed #D4D4D8',
                  borderRadius: '8px',
                  padding: '40px',
                  textAlign: 'center',
                  marginBottom: '16px'
                }}>
                  <input
                    type="file"
                    multiple
                    onChange={(e) => handleFileUpload(e.target.files)}
                    style={{ display: 'none' }}
                    id="file-upload"
                  />
                  <label
                    htmlFor="file-upload"
                    style={{
                      cursor: 'pointer',
                      color: '#081028',
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px'
                    }}
                  >
                    <div style={{ marginBottom: '8px', fontSize: '24px' }}>📄</div>
                    <div style={{ fontWeight: 500 }}>Click to upload files</div>
                    <div style={{ fontSize: '12px', color: '#71717A', marginTop: '4px' }}>
                      PDF, DOCX, DOC, TXT (max 50MB each)
                    </div>
                  </label>
                </div>
              </div>
            )}

            {/* Text Paste Mode */}
            {uploadMode === 'text' && (
              <div>
                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px'
                  }}>
                    Title *
                  </label>
                  <input
                    type="text"
                    value={textTitle}
                    onChange={e => setTextTitle(e.target.value)}
                    placeholder="Document title"
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px'
                  }}>
                    Content * (minimum 50 characters)
                  </label>
                  <textarea
                    value={textContent}
                    onChange={e => setTextContent(e.target.value)}
                    placeholder="Paste or type your content here..."
                    rows={10}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif',
                      resize: 'vertical'
                    }}
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px'
                  }}>
                    Classification
                  </label>
                  <select
                    value={textClassification}
                    onChange={e => setTextClassification(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="work">Work</option>
                    <option value="personal">Personal</option>
                    <option value="spam">Spam</option>
                  </select>
                </div>

                <button
                  onClick={handleTextPaste}
                  disabled={uploading || !textTitle.trim() || !textContent.trim()}
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: uploading || !textTitle.trim() || !textContent.trim() ? '#9ca3af' : '#081028',
                    color: '#FFE2BF',
                    fontSize: '14px',
                    fontWeight: 500,
                    cursor: uploading || !textTitle.trim() || !textContent.trim() ? 'not-allowed' : 'pointer',
                    fontFamily: '"Work Sans", sans-serif'
                  }}
                >
                  {uploading ? 'Adding Document...' : 'Add Document'}
                </button>
              </div>
            )}

            {/* URL Mode */}
            {uploadMode === 'url' && (
              <div>
                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px'
                  }}>
                    URL *
                  </label>
                  <input
                    type="url"
                    value={urlInput}
                    onChange={e => setUrlInput(e.target.value)}
                    placeholder="https://example.com/document.pdf"
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  />
                  <div style={{
                    marginTop: '4px',
                    fontSize: '12px',
                    color: '#71717A',
                    fontFamily: 'Inter, sans-serif'
                  }}>
                    Supports: Web pages (HTML), PDF files, Google Docs (public links)
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px'
                  }}>
                    Classification
                  </label>
                  <select
                    value={textClassification}
                    onChange={e => setTextClassification(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="work">Work</option>
                    <option value="personal">Personal</option>
                    <option value="spam">Spam</option>
                  </select>
                </div>

                <button
                  onClick={handleUrlAdd}
                  disabled={uploading || !urlInput.trim()}
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: uploading || !urlInput.trim() ? '#9ca3af' : '#081028',
                    color: '#FFE2BF',
                    fontSize: '14px',
                    fontWeight: 500,
                    cursor: uploading || !urlInput.trim() ? 'not-allowed' : 'pointer',
                    fontFamily: '"Work Sans", sans-serif'
                  }}
                >
                  {uploading ? 'Fetching Content...' : 'Add from URL'}
                </button>
              </div>
            )}

            {uploading && uploadMode === 'file' && (
              <div style={{
                textAlign: 'center',
                padding: '20px',
                color: '#081028',
                fontFamily: 'Inter, sans-serif',
                fontSize: '14px'
              }}>
                Uploading files...
              </div>
            )}
          </div>
        </div>
      )}

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
              backgroundColor: '#FFE2BF',
              borderRadius: '12px',
              padding: '32px',
              border: '1px solid #081028',
              boxShadow: '4px 4px 8px rgba(16, 25, 52, 0.40)'
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

      {/* Video Generation Modal */}
      {showVideoModal && (
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
          onClick={() => !generatingVideo && setShowVideoModal(false)}
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '12px',
              padding: '32px',
              maxWidth: '600px',
              width: '90%',
              maxHeight: '80vh',
              overflow: 'auto',
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
            }}
            onClick={e => e.stopPropagation()}
          >
            {!generatingVideo ? (
              <>
                <h2 style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '24px',
                  fontWeight: 600,
                  marginBottom: '8px',
                  color: '#081028'
                }}>
                  🎬 Generate Training Video
                </h2>

                <p style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '14px',
                  color: '#71717A',
                  marginBottom: '24px'
                }}>
                  Create an AI-powered training video from {documents.filter(d => d.selected).length} selected document(s) using Gamma AI
                </p>

                {/* Video Title */}
                <div style={{ marginBottom: '20px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px',
                    color: '#081028'
                  }}>
                    Video Title *
                  </label>
                  <input
                    type="text"
                    value={videoTitle}
                    onChange={e => setVideoTitle(e.target.value)}
                    placeholder="e.g., Onboarding Training - Week 1"
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  />
                </div>

                {/* Video Description */}
                <div style={{ marginBottom: '24px' }}>
                  <label style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '14px',
                    fontWeight: 500,
                    display: 'block',
                    marginBottom: '8px',
                    color: '#081028'
                  }}>
                    Description (Optional)
                  </label>
                  <textarea
                    value={videoDescription}
                    onChange={e => setVideoDescription(e.target.value)}
                    placeholder="Brief description of what this training video covers..."
                    rows={3}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      fontSize: '14px',
                      fontFamily: 'Inter, sans-serif',
                      resize: 'vertical'
                    }}
                  />
                </div>

                {/* Selected Documents List */}
                <div style={{
                  marginBottom: '24px',
                  padding: '16px',
                  backgroundColor: '#F9FAFB',
                  borderRadius: '8px',
                  border: '1px solid #E5E7EB'
                }}>
                  <p style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '13px',
                    fontWeight: 500,
                    marginBottom: '8px',
                    color: '#081028'
                  }}>
                    Selected Documents ({documents.filter(d => d.selected).length}):
                  </p>
                  <ul style={{
                    margin: 0,
                    paddingLeft: '20px',
                    maxHeight: '120px',
                    overflow: 'auto'
                  }}>
                    {documents.filter(d => d.selected).map(doc => (
                      <li key={doc.id} style={{
                        fontFamily: 'Inter, sans-serif',
                        fontSize: '12px',
                        color: '#6B7280',
                        marginBottom: '4px'
                      }}>
                        {doc.name}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Info Box */}
                <div style={{
                  padding: '12px 16px',
                  backgroundColor: '#FFF7ED',
                  border: '1px solid #FDBA74',
                  borderRadius: '8px',
                  marginBottom: '24px'
                }}>
                  <p style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '12px',
                    color: '#9A3412',
                    margin: 0
                  }}>
                    ⚡ Gamma AI will generate a professional presentation, convert it to video with narration. This typically takes 3-5 minutes.
                  </p>
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => setShowVideoModal(false)}
                    style={{
                      padding: '10px 20px',
                      borderRadius: '8px',
                      border: '1px solid #D4D4D8',
                      backgroundColor: '#FFFFFF',
                      color: '#081028',
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px',
                      fontWeight: 500,
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={createVideo}
                    disabled={!videoTitle.trim()}
                    style={{
                      padding: '10px 20px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: !videoTitle.trim() ? '#ccc' : '#FF6B35',
                      color: '#FFFFFF',
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px',
                      fontWeight: 600,
                      cursor: !videoTitle.trim() ? 'not-allowed' : 'pointer',
                      opacity: !videoTitle.trim() ? 0.6 : 1
                    }}
                  >
                    Generate Video
                  </button>
                </div>
              </>
            ) : (
              /* Video Generation Progress */
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <div style={{
                  width: '80px',
                  height: '80px',
                  margin: '0 auto 24px',
                  borderRadius: '50%',
                  border: '4px solid #FFE2BF',
                  borderTop: '4px solid #FF6B35',
                  animation: 'spin 1s linear infinite'
                }}>
                  <style jsx>{`
                    @keyframes spin {
                      0% { transform: rotate(0deg); }
                      100% { transform: rotate(360deg); }
                    }
                  `}</style>
                </div>

                <h3 style={{
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '20px',
                  fontWeight: 600,
                  marginBottom: '12px',
                  color: '#081028'
                }}>
                  Generating Your Video...
                </h3>

                {videoProgress && (
                  <>
                    <p style={{
                      fontFamily: 'Inter, sans-serif',
                      fontSize: '14px',
                      color: '#6B7280',
                      marginBottom: '16px'
                    }}>
                      {videoProgress.current_step}
                    </p>

                    {/* Progress Bar */}
                    <div style={{
                      width: '100%',
                      height: '8px',
                      backgroundColor: '#E5E7EB',
                      borderRadius: '4px',
                      overflow: 'hidden',
                      marginBottom: '8px'
                    }}>
                      <div style={{
                        width: `${videoProgress.progress_percent}%`,
                        height: '100%',
                        backgroundColor: '#FF6B35',
                        transition: 'width 0.3s ease'
                      }} />
                    </div>

                    <p style={{
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px',
                      fontWeight: 600,
                      color: '#081028'
                    }}>
                      {videoProgress.progress_percent}% Complete
                    </p>
                  </>
                )}

                <p style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '12px',
                  color: '#9CA3AF',
                  marginTop: '24px'
                }}>
                  This may take a few minutes. Please don't close this window.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
