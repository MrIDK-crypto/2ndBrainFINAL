'use client'

import React, { useState, useEffect } from 'react'
import Sidebar from '../shared/Sidebar'
import Image from 'next/image'
import axios from 'axios'
import { useAuthHeaders } from '@/contexts/AuthContext'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003') + '/api'

interface Video {
  id: string
  title: string
  description: string | null
  status: string
  progress_percent: number
  file_path: string | null
  thumbnail_path: string | null
  duration_seconds: number | null
  created_at: string
  source_type: string
  slides_count: number | null
}

interface VideoPlayerModalProps {
  video: Video
  onClose: () => void
}

const VideoPlayerModal = ({ video, onClose }: VideoPlayerModalProps) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return 'Unknown'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      })
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
        backgroundColor: 'rgba(8, 16, 40, 0.9)',
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
          boxShadow: '4px 4px 12px rgba(16, 25, 52, 0.50)',
          maxWidth: '1200px',
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
                marginBottom: '8px'
              }}
            >
              {video.title}
            </h2>
            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              {video.duration_seconds && (
                <span style={{ color: '#7E89AC', fontSize: '13px', fontFamily: '"Work Sans", sans-serif' }}>
                  Duration: {formatDuration(video.duration_seconds)}
                </span>
              )}
              {video.slides_count && (
                <span style={{ color: '#7E89AC', fontSize: '13px', fontFamily: '"Work Sans", sans-serif' }}>
                  {video.slides_count} slides
                </span>
              )}
              <span style={{ color: '#7E89AC', fontSize: '13px', fontFamily: '"Work Sans", sans-serif' }}>
                Created: {formatDate(video.created_at)}
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

        {/* Video Player */}
        <div
          style={{
            flex: 1,
            backgroundColor: '#000000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '400px'
          }}
        >
          {video.file_path ? (
            <video
              controls
              autoPlay
              style={{
                width: '100%',
                height: '100%',
                maxHeight: '600px'
              }}
            >
              <source src={video.file_path} type="video/mp4" />
              Your browser does not support the video tag.
            </video>
          ) : (
            <div style={{ color: '#FFFFFF', fontFamily: '"Work Sans", sans-serif', fontSize: '16px' }}>
              Video not available
            </div>
          )}
        </div>

        {/* Description */}
        {video.description && (
          <div
            style={{
              padding: '16px 24px',
              borderTop: '1px solid #081028',
              backgroundColor: '#FFF3E4'
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
              Description
            </h3>
            <p
              style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '13px',
                lineHeight: '20px'
              }}
            >
              {video.description}
            </p>
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 24px',
            borderTop: '1px solid #081028',
            backgroundColor: '#FFE2BF'
          }}
        >
          <div style={{ display: 'flex', gap: '12px' }}>
            {video.file_path && (
              <a
                href={video.file_path}
                download
                style={{
                  display: 'flex',
                  padding: '10px 24px',
                  justifyContent: 'center',
                  alignItems: 'center',
                  borderRadius: '4px',
                  backgroundColor: '#05C168',
                  color: '#FFFFFF',
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '14px',
                  fontWeight: 600,
                  textDecoration: 'none'
                }}
              >
                Download Video
              </a>
            )}
            {video.file_path && (
              <button
                onClick={() => {
                  navigator.clipboard.writeText(video.file_path!)
                  alert('Video link copied to clipboard!')
                }}
                style={{
                  display: 'flex',
                  padding: '10px 24px',
                  justifyContent: 'center',
                  alignItems: 'center',
                  borderRadius: '4px',
                  backgroundColor: '#FFFFFF',
                  color: '#081028',
                  border: '1px solid #081028',
                  cursor: 'pointer',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '14px',
                  fontWeight: 600
                }}
              >
                Share Link
              </button>
            )}
          </div>
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

const VideoCard = ({ video, onClick }: { video: Video, onClick: () => void }) => {
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      })
    } catch {
      return dateStr
    }
  }

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return 'Duration unknown'
    const mins = Math.floor(seconds / 60)
    return `${mins} min`
  }

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'documents':
        return '/Development.svg'
      case 'knowledge_gaps':
        return '/Pencil.svg'
      default:
        return '/Development.svg'
    }
  }

  const getSourceLabel = (sourceType: string) => {
    switch (sourceType) {
      case 'documents':
        return 'From Documents'
      case 'knowledge_gaps':
        return 'Training Q&A'
      default:
        return 'Training Video'
    }
  }

  return (
    <div
      onClick={onClick}
      className="flex flex-col items-start gap-[30px] bg-secondary rounded-xl overflow-hidden border border-gray-200 hover:shadow-lg transition-shadow cursor-pointer"
      style={{
        width: '328px',
        minHeight: '380px'
      }}
    >
      {/* Thumbnail Preview */}
      <div
        className="w-full bg-gray-200 flex items-center justify-center overflow-hidden"
        style={{ height: '200px' }}
      >
        {video.thumbnail_path ? (
          <img
            src={video.thumbnail_path}
            alt={video.title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-orange-300 to-orange-500 flex items-center justify-center">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M8 5V19L19 12L8 5Z" fill="white" />
            </svg>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="px-5 pb-5 flex-1 flex flex-col justify-between w-full">
        {/* Top section */}
        <div>
          <h3 className="text-neutral-800 font-work text-base font-semibold mb-2 line-clamp-2">
            {video.title}
          </h3>
          {video.description && (
            <p className="text-gray-600 font-sans text-sm line-clamp-2">
              {video.description}
            </p>
          )}
          <div className="mt-2 text-gray-500 text-xs">
            {formatDate(video.created_at)} • {formatDuration(video.duration_seconds)}
          </div>
        </div>

        {/* Divider */}
        <div
          className="my-3"
          style={{
            width: '100%',
            height: '0',
            borderTop: '0.6px solid #0B1739'
          }}
        />

        {/* Bottom section - Status & Source tag */}
        <div className="flex items-center justify-between">
          <div
            className="flex items-center gap-2 px-[6px] py-[3px] rounded-sm border"
            style={{
              borderColor: '#FFE2BF',
              backgroundColor: '#FFE2BF'
            }}
          >
            <Image
              src={getSourceIcon(video.source_type)}
              alt={video.source_type}
              width={14}
              height={14}
            />
            <span
              className="font-work font-medium"
              style={{
                color: '#081028',
                fontSize: '14px',
                lineHeight: '14px'
              }}
            >
              {getSourceLabel(video.source_type)}
            </span>
          </div>

          {/* Status badge */}
          {video.status === 'completed' ? (
            <div className="flex items-center gap-1">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="7" fill="#05C168"/>
                <path d="M5 8L7 10L11 6" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
          ) : (
            <span className="text-xs text-gray-500">{video.status}</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function TrainingGuides() {
  const [activeItem, setActiveItem] = useState('Training Guides')
  const [videos, setVideos] = useState<Video[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null)
  const authHeaders = useAuthHeaders()

  useEffect(() => {
    loadVideos()
  }, [])

  const loadVideos = async () => {
    try {
      const response = await axios.get(`${API_BASE}/videos?status=completed`, {
        headers: authHeaders
      })

      if (response.data.success) {
        setVideos(response.data.videos)
      }
    } catch (error) {
      console.error('Error loading videos:', error)
    } finally {
      setLoading(false)
    }
  }

  const completedVideos = videos.filter(v => v.status === 'completed')
  const documentVideos = completedVideos.filter(v => v.source_type === 'documents')
  const gapVideos = completedVideos.filter(v => v.source_type === 'knowledge_gaps')

  const totalDuration = completedVideos.reduce((sum, v) => sum + (v.duration_seconds || 0), 0)
  const totalHours = Math.floor(totalDuration / 3600)
  const totalMins = Math.floor((totalDuration % 3600) / 60)

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      {/* Sidebar */}
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="flex items-center px-8 py-4 bg-primary">
          <div className="flex-1 flex justify-center">
            <h1 className="text-neutral-800 font-work text-xl font-semibold">
              Training Guides
            </h1>
          </div>

          <div className="flex items-center gap-4">
            <input
              type="text"
              placeholder="Search videos..."
              className="h-[42px] px-4 rounded border border-neutral-500 bg-secondary text-sm outline-none"
              style={{ width: '352px' }}
            />
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-neutral-800 font-work text-lg">Loading training videos...</div>
            </div>
          ) : completedVideos.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <div className="text-neutral-800 font-work text-lg">No training videos yet</div>
              <p className="text-gray-600 text-sm">Generate videos from Documents or Knowledge Gaps to get started</p>
            </div>
          ) : (
            <div
              className="flex items-start gap-[30px]"
            >
              {/* Document Videos Column */}
              {documentVideos.length > 0 && (
                <div
                  className="flex flex-col items-start gap-[30px]"
                >
                  <div className="flex items-center gap-2">
                    <h2
                      className="font-work font-medium"
                      style={{
                        color: '#081028',
                        fontSize: '14px',
                        lineHeight: '14px'
                      }}
                    >
                      Document Videos
                    </h2>
                    <div
                      className="flex items-center px-[5px] py-[1px] rounded-sm border"
                      style={{
                        borderColor: '#FFE2BF',
                        backgroundColor: '#FFE2BF'
                      }}
                    >
                      <span
                        className="font-work font-medium text-xs"
                        style={{ color: '#081028' }}
                      >
                        {documentVideos.length} video{documentVideos.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-[30px]">
                    {documentVideos.map((video) => (
                      <VideoCard
                        key={video.id}
                        video={video}
                        onClick={() => setSelectedVideo(video)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Training Q&A Videos Column */}
              {gapVideos.length > 0 && (
                <div
                  className="flex flex-col items-start gap-[30px]"
                >
                  <div className="flex items-center gap-2">
                    <h2
                      className="font-work font-medium"
                      style={{
                        color: '#081028',
                        fontSize: '14px',
                        lineHeight: '14px'
                      }}
                    >
                      Training Q&A Videos
                    </h2>
                    <div
                      className="flex items-center px-[5px] py-[1px] rounded-sm border"
                      style={{
                        borderColor: '#FFE2BF',
                        backgroundColor: '#FFE2BF'
                      }}
                    >
                      <span
                        className="font-work font-medium text-xs"
                        style={{ color: '#081028' }}
                      >
                        {gapVideos.length} video{gapVideos.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-[30px]">
                    {gapVideos.map((video) => (
                      <VideoCard
                        key={video.id}
                        video={video}
                        onClick={() => setSelectedVideo(video)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* All Videos Column (if both types exist) */}
              {documentVideos.length > 0 && gapVideos.length > 0 && (
                <div
                  className="flex flex-col items-start gap-[30px]"
                >
                  <div className="flex items-center gap-2">
                    <h2
                      className="font-work font-medium"
                      style={{
                        color: '#081028',
                        fontSize: '14px',
                        lineHeight: '14px'
                      }}
                    >
                      All Videos
                    </h2>
                    <div
                      className="flex items-center px-[5px] py-[1px] rounded-sm border"
                      style={{
                        borderColor: '#FFE2BF',
                        backgroundColor: '#FFE2BF'
                      }}
                    >
                      <span
                        className="font-work font-medium text-xs"
                        style={{ color: '#081028' }}
                      >
                        {totalHours > 0 && `${totalHours}h `}{totalMins}min total
                      </span>
                    </div>
                  </div>

                  <div className="text-gray-600 text-sm">
                    {completedVideos.length} total training video{completedVideos.length !== 1 ? 's' : ''}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Video Player Modal */}
      {selectedVideo && (
        <VideoPlayerModal
          video={selectedVideo}
          onClose={() => setSelectedVideo(null)}
        />
      )}
    </div>
  )
}
