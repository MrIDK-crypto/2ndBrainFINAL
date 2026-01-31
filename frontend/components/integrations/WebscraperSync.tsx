'use client'

import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : 'http://localhost:5003/api'

interface SyncProgress {
  status: 'idle' | 'syncing' | 'parsing' | 'embedding' | 'completed' | 'error'
  progress: number
  documentsFound: number
  documentsParsed: number
  documentsEmbedded: number
  currentFile?: string
  error?: string
}

interface Props {
  onComplete?: () => void
}

export default function WebscraperSync({ onComplete }: Props) {
  const [url, setUrl] = useState('')
  const [maxPages, setMaxPages] = useState(50)
  const [maxDepth, setMaxDepth] = useState(3)
  const [syncing, setSyncing] = useState(false)
  const [progress, setProgress] = useState<SyncProgress>({
    status: 'idle',
    progress: 0,
    documentsFound: 0,
    documentsParsed: 0,
    documentsEmbedded: 0
  })

  // Use ref to track interval ID so we can clear it
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [])

  const getAuthToken = () => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('authToken')
  }

  const pollSyncStatus = async () => {
    const token = getAuthToken()
    if (!token) return

    try {
      const response = await axios.get(`${API_BASE}/integrations/webscraper/sync/status`, {
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.data.success) {
        const status = response.data.status
        setProgress({
          status: status.status,
          progress: status.progress || 0,
          documentsFound: status.documents_found || 0,
          documentsParsed: status.documents_parsed || 0,
          documentsEmbedded: status.documents_embedded || 0,
          currentFile: status.current_file,
          error: status.error
        })

        // Stop polling if completed or errored
        if (status.status === 'completed' || status.status === 'error') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          setSyncing(false)

          if (status.status === 'completed' && onComplete) {
            onComplete()
          }
        }
      }
    } catch (error) {
      console.error('Error polling sync status:', error)
    }
  }

  const startSync = async () => {
    if (!url.trim()) {
      alert('Please enter a URL')
      return
    }

    const token = getAuthToken()
    if (!token) {
      alert('Not authenticated. Please log in.')
      return
    }

    setSyncing(true)
    setProgress({
      status: 'syncing',
      progress: 0,
      documentsFound: 0,
      documentsParsed: 0,
      documentsEmbedded: 0
    })

    try {
      // Configure webscraper
      await axios.post(
        `${API_BASE}/integrations/webscraper/configure`,
        {
          start_url: url,
          max_pages: maxPages,
          max_depth: maxDepth,
          priority_paths: []
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      // Start sync
      await axios.post(
        `${API_BASE}/integrations/webscraper/sync`,
        {},
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      )

      // Start polling every 2 seconds
      pollingIntervalRef.current = setInterval(pollSyncStatus, 2000)
    } catch (error: any) {
      console.error('Error starting sync:', error)
      setSyncing(false)
      setProgress({
        status: 'error',
        progress: 0,
        documentsFound: 0,
        documentsParsed: 0,
        documentsEmbedded: 0,
        error: error.response?.data?.error || error.message || 'Failed to start sync'
      })
    }
  }

  const stopSync = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    setSyncing(false)
    setProgress({
      status: 'idle',
      progress: 0,
      documentsFound: 0,
      documentsParsed: 0,
      documentsEmbedded: 0
    })
  }

  return (
    <div className="p-6 bg-gray-800 rounded-lg">
      <h2 className="text-2xl font-bold mb-4">Website Scraper</h2>

      {/* Configuration */}
      <div className="space-y-4 mb-6">
        <div>
          <label className="block text-sm font-medium mb-2">Website URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            disabled={syncing}
            className="w-full px-4 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Max Pages</label>
            <input
              type="number"
              value={maxPages}
              onChange={(e) => setMaxPages(parseInt(e.target.value) || 50)}
              disabled={syncing}
              min="1"
              max="500"
              className="w-full px-4 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Max Depth</label>
            <input
              type="number"
              value={maxDepth}
              onChange={(e) => setMaxDepth(parseInt(e.target.value) || 3)}
              disabled={syncing}
              min="1"
              max="10"
              className="w-full px-4 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Control Buttons */}
      <div className="flex gap-4 mb-6">
        <button
          onClick={startSync}
          disabled={syncing}
          className={`px-6 py-2 rounded font-medium ${
            syncing
              ? 'bg-gray-600 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {syncing ? 'Syncing...' : 'Start Sync'}
        </button>

        {syncing && (
          <button
            onClick={stopSync}
            className="px-6 py-2 rounded font-medium bg-red-600 hover:bg-red-700"
          >
            Stop
          </button>
        )}
      </div>

      {/* Progress Display */}
      {progress.status !== 'idle' && (
        <div className="space-y-4">
          {/* Progress Bar */}
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="capitalize">{progress.status}</span>
              <span>{progress.progress}%</span>
            </div>
            <div className="w-full h-3 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  progress.status === 'completed'
                    ? 'bg-green-500'
                    : progress.status === 'error'
                    ? 'bg-red-500'
                    : 'bg-blue-500'
                }`}
                style={{ width: `${progress.progress}%` }}
              />
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="bg-gray-700 p-3 rounded">
              <div className="text-2xl font-bold">{progress.documentsFound}</div>
              <div className="text-sm text-gray-400">Found</div>
            </div>
            <div className="bg-gray-700 p-3 rounded">
              <div className="text-2xl font-bold">{progress.documentsParsed}</div>
              <div className="text-sm text-gray-400">Parsed</div>
            </div>
            <div className="bg-gray-700 p-3 rounded">
              <div className="text-2xl font-bold">{progress.documentsEmbedded}</div>
              <div className="text-sm text-gray-400">Embedded</div>
            </div>
          </div>

          {/* Current File */}
          {progress.currentFile && (
            <div className="text-sm text-gray-400">
              Processing: {progress.currentFile}
            </div>
          )}

          {/* Error Message */}
          {progress.error && (
            <div className="bg-red-900/50 border border-red-500 rounded p-4 text-red-200">
              {progress.error}
            </div>
          )}

          {/* Success Message */}
          {progress.status === 'completed' && (
            <div className="bg-green-900/50 border border-green-500 rounded p-4 text-green-200">
              Sync completed! {progress.documentsParsed} documents processed.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
