'use client'

import React, { useState, useEffect, useRef } from 'react'
import Sidebar from '../shared/Sidebar'
import axios from 'axios'
import { useAuth, useAuthHeaders } from '@/contexts/AuthContext'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5003') + '/api'
const MAX_QUESTIONS = 30 // Cap at 30 questions

interface KnowledgeGap {
  id: string
  description: string
  project: string
  answered?: boolean
  answer?: string
}

export default function KnowledgeGaps() {
  const [activeItem, setActiveItem] = useState('Knowledge Gaps')
  const [gaps, setGaps] = useState<KnowledgeGap[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'unanswered' | 'answered'>('all')
  const [selectedGap, setSelectedGap] = useState<KnowledgeGap | null>(null)
  const [answer, setAnswer] = useState('')
  const [generating, setGenerating] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)

  // Video generation state
  const [showVideoModal, setShowVideoModal] = useState(false)
  const [videoTitle, setVideoTitle] = useState('')
  const [videoDescription, setVideoDescription] = useState('')
  const [includeAnswers, setIncludeAnswers] = useState(true)
  const [generatingVideo, setGeneratingVideo] = useState(false)
  const [videoProgress, setVideoProgress] = useState<{
    status: string
    progress_percent: number
    current_step: string
  } | null>(null)
  const [createdVideoId, setCreatedVideoId] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const authHeaders = useAuthHeaders()
  const { token } = useAuth()

  useEffect(() => {
    if (token) loadKnowledgeGaps()
  }, [token])

  useEffect(() => {
    if (selectedGap) {
      setAnswer(selectedGap.answer || '')
    }
  }, [selectedGap])

  const loadKnowledgeGaps = async () => {
    try {
      const response = await axios.get(`${API_BASE}/knowledge/gaps`, { headers: authHeaders })

      if (response.data.success && response.data.gaps) {
        const allGaps: KnowledgeGap[] = []

        response.data.gaps.forEach((gap: any) => {
          const groupName = gap.title || gap.category || 'General'
          const questions = gap.questions || []

          if (questions.length === 0 && gap.description) {
            allGaps.push({
              id: gap.id,
              description: gap.description,
              project: groupName,
              answered: gap.status === 'answered' || gap.status === 'verified' || gap.status === 'closed',
              answer: ''
            })
          } else {
            questions.forEach((question: any, qIndex: number) => {
              const questionText = typeof question === 'string' ? question : question.text || ''
              const isAnswered = typeof question === 'object' ? question.answered : false
              const answerObj = gap.answers?.find((a: any) => a.question_index === qIndex)

              allGaps.push({
                id: `${gap.id}_${qIndex}`,
                description: questionText,
                project: groupName,
                answered: isAnswered || gap.status === 'answered' || gap.status === 'verified' || gap.status === 'closed',
                answer: answerObj?.answer_text || ''
              })
            })
          }
        })

        // Cap at MAX_QUESTIONS, prioritizing unanswered
        const unanswered = allGaps.filter(g => !g.answered)
        const answered = allGaps.filter(g => g.answered)
        const capped = [...unanswered, ...answered].slice(0, MAX_QUESTIONS)

        setGaps(capped)
      }
    } catch (error) {
      console.error('Error loading knowledge gaps:', error)
    } finally {
      setLoading(false)
    }
  }

  const generateQuestions = async () => {
    setGenerating(true)
    try {
      const response = await axios.post(`${API_BASE}/knowledge/analyze`, {
        force: true,
        include_pending: true
      }, { headers: authHeaders })

      if (response.data.success) {
        await loadKnowledgeGaps()
      }
    } catch (error) {
      console.error('Error analyzing documents:', error)
    } finally {
      setGenerating(false)
    }
  }

  const handleAnswerQuestion = async () => {
    if (!selectedGap || !answer.trim() || submitting) return

    setSubmitting(true)
    try {
      const idParts = selectedGap.id.split('_')
      const questionIndex = idParts.length > 1 ? parseInt(idParts[idParts.length - 1]) : 0
      const originalGapId = idParts.length > 1 ? idParts.slice(0, -1).join('_') : selectedGap.id

      await axios.post(`${API_BASE}/knowledge/gaps/${originalGapId}/answers`, {
        question_index: questionIndex,
        answer_text: answer
      }, { headers: authHeaders })

      setGaps(prev => prev.map(g =>
        g.id === selectedGap.id ? { ...g, answered: true, answer } : g
      ))

      setSelectedGap({ ...selectedGap, answered: true, answer })
    } catch (error) {
      console.error('Error submitting answer:', error)
    } finally {
      setSubmitting(false)
    }
  }

  // Voice recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop())
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' })

        if (audioBlob.size > 0) {
          setIsTranscribing(true)
          try {
            const formData = new FormData()
            formData.append('audio', audioBlob, 'recording.webm')
            const response = await axios.post(`${API_BASE}/knowledge/transcribe`, formData, {
              headers: { ...authHeaders, 'Content-Type': 'multipart/form-data' }
            })
            if (response.data.transcript) {
              setAnswer(prev => prev ? `${prev} ${response.data.transcript}` : response.data.transcript)
            }
          } catch (error) {
            console.error('Transcription error:', error)
          } finally {
            setIsTranscribing(false)
          }
        }
        setIsListening(false)
      }

      mediaRecorder.start(1000)
      setIsListening(true)
    } catch (error) {
      console.error('Microphone error:', error)
      setIsListening(false)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state !== 'inactive') {
      mediaRecorderRef.current?.stop()
    }
  }

  const toggleRecording = () => {
    if (isListening) stopRecording()
    else startRecording()
  }

  // Video generation functions
  const handleGenerateTrainingVideo = () => {
    if (gaps.length === 0) {
      alert('No knowledge gaps available. Please analyze documents first.')
      return
    }
    setVideoTitle('')
    setVideoDescription('')
    setIncludeAnswers(true)
    setShowVideoModal(true)
  }

  const createTrainingVideo = async () => {
    if (!videoTitle.trim()) {
      alert('Please enter a video title')
      return
    }

    if (gaps.length === 0) {
      alert('No knowledge gaps available')
      return
    }

    setGeneratingVideo(true)
    try {
      // Get actual gap IDs from the backend format
      const gapIds = gaps.map(g => {
        // If the ID contains an underscore, it's a question index - extract the original gap ID
        const gapId = g.id.includes('_') ? g.id.split('_')[0] : g.id
        return gapId
      }).filter((id, index, self) => self.indexOf(id) === index) // Remove duplicates

      const response = await axios.post(
        `${API_BASE}/videos`,
        {
          title: videoTitle,
          description: videoDescription || undefined,
          source_type: 'knowledge_gaps',
          source_ids: gapIds,
          include_answers: includeAnswers
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
      console.error('Error creating training video:', error)
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
        const status = response.data.status
        setVideoProgress({
          status: status.status,
          progress_percent: status.progress_percent || 0,
          current_step: status.current_step || 'Processing...'
        })

        if (status.status === 'completed') {
          // Video is ready!
          setTimeout(() => {
            setGeneratingVideo(false)
            setShowVideoModal(false)
            setVideoProgress(null)
            setCreatedVideoId(null)
            alert('Training video generated successfully! Redirecting to Training Guides...')
            window.location.href = '/training-guides'
          }, 1500)
        } else if (status.status === 'failed') {
          setGeneratingVideo(false)
          setVideoProgress(null)
          alert('Video generation failed: ' + (status.error_message || 'Unknown error'))
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

  // Filter gaps
  const filteredGaps = gaps.filter(g => {
    if (filter === 'unanswered' && g.answered) return false
    if (filter === 'answered' && !g.answered) return false
    return true
  })

  const totalAnswered = gaps.filter(g => g.answered).length
  const totalPending = gaps.length - totalAnswered

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      <Sidebar activeItem={activeItem} onItemClick={setActiveItem} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="px-8 py-6 bg-primary">
          <div className="flex items-start justify-between">
            <div>
              <h1 style={{
                color: '#081028',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '24px',
                fontWeight: 600,
                letterSpacing: '-0.01em'
              }}>
                Knowledge Gaps
              </h1>
              <p style={{
                color: '#7E89AC',
                fontFamily: '"Work Sans", sans-serif',
                fontSize: '14px',
                marginTop: '2px'
              }}>
                {totalPending} questions remaining · {totalAnswered} completed
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={handleGenerateTrainingVideo}
                disabled={gaps.length === 0}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 18px',
                  borderRadius: '8px',
                  backgroundColor: gaps.length === 0 ? '#ccc' : '#FF6B35',
                  color: 'white',
                  border: 'none',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: gaps.length === 0 ? 'not-allowed' : 'pointer',
                  opacity: gaps.length === 0 ? 0.6 : 1
                }}
              >
                🎬 Generate Training Video
              </button>

              <button
                onClick={generateQuestions}
                disabled={generating}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 18px',
                  borderRadius: '8px',
                  backgroundColor: '#081028',
                  color: 'white',
                  border: 'none',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: generating ? 'not-allowed' : 'pointer',
                  opacity: generating ? 0.7 : 1
                }}
              >
                {generating ? 'Analyzing...' : 'Analyze Documents'}
              </button>
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ marginTop: '20px' }}>
            <div style={{
              height: '6px',
              backgroundColor: 'rgba(8, 16, 40, 0.08)',
              borderRadius: '3px',
              overflow: 'hidden'
            }}>
              <div style={{
                width: `${gaps.length > 0 ? (totalAnswered / gaps.length) * 100 : 0}%`,
                height: '100%',
                backgroundColor: '#10B981',
                borderRadius: '3px',
                transition: 'width 0.3s ease'
              }} />
            </div>
          </div>

          {/* Filter tabs */}
          <div style={{ display: 'flex', gap: '4px', marginTop: '20px' }}>
            {(['all', 'unanswered', 'answered'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  backgroundColor: filter === f ? '#081028' : 'transparent',
                  color: filter === f ? 'white' : '#7E89AC',
                  border: 'none',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer'
                }}
              >
                {f === 'all' ? `All (${gaps.length})` :
                 f === 'unanswered' ? `Pending (${totalPending})` :
                 `Done (${totalAnswered})`}
              </button>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Questions list */}
          <div style={{
            flex: selectedGap ? '0 0 50%' : 1,
            overflowY: 'auto',
            padding: '0 32px 32px',
            backgroundColor: '#FFF3E4'
          }}>
            {loading ? (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '200px',
                color: '#7E89AC',
                fontFamily: '"Work Sans", sans-serif'
              }}>
                Loading...
              </div>
            ) : filteredGaps.length === 0 ? (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '200px',
                color: '#7E89AC',
                fontFamily: '"Work Sans", sans-serif',
                textAlign: 'center'
              }}>
                <p style={{ fontSize: '14px' }}>No questions found</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {filteredGaps.map((gap, index) => (
                  <div
                    key={gap.id}
                    onClick={() => setSelectedGap(gap)}
                    style={{
                      padding: '16px 20px',
                      borderRadius: '8px',
                      backgroundColor: selectedGap?.id === gap.id ? '#FFE2BF' : 'white',
                      border: selectedGap?.id === gap.id ? '2px solid #081028' : '1px solid rgba(8, 16, 40, 0.06)',
                      cursor: 'pointer',
                      transition: 'all 0.15s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                      {/* Number */}
                      <span style={{
                        color: gap.answered ? '#10B981' : '#7E89AC',
                        fontFamily: '"Work Sans", sans-serif',
                        fontSize: '13px',
                        fontWeight: 600,
                        minWidth: '24px'
                      }}>
                        {gap.answered ? '✓' : `${index + 1}.`}
                      </span>

                      {/* Question */}
                      <p style={{
                        color: gap.answered ? '#7E89AC' : '#081028',
                        fontFamily: '"Work Sans", sans-serif',
                        fontSize: '14px',
                        lineHeight: '1.5',
                        textDecoration: gap.answered ? 'line-through' : 'none',
                        flex: 1
                      }}>
                        {gap.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Answer panel */}
          {selectedGap && (
            <div style={{
              flex: '0 0 50%',
              borderLeft: '1px solid rgba(8, 16, 40, 0.08)',
              backgroundColor: 'white',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden'
            }}>
              {/* Panel header */}
              <div style={{
                padding: '16px 24px',
                borderBottom: '1px solid rgba(8, 16, 40, 0.06)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end'
              }}>
                <button
                  onClick={() => setSelectedGap(null)}
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: 'transparent',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#7E89AC'
                  }}
                >
                  ✕
                </button>
              </div>

              {/* Content */}
              <div style={{ padding: '24px', flex: 1, overflowY: 'auto' }}>
                <p style={{
                  color: '#081028',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '16px',
                  fontWeight: 500,
                  lineHeight: '1.6',
                  marginBottom: '24px'
                }}>
                  {selectedGap.description}
                </p>

                <p style={{
                  color: '#7E89AC',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: '10px'
                }}>
                  Your Answer
                </p>

                {selectedGap.answered && selectedGap.answer ? (
                  <div style={{
                    padding: '14px',
                    backgroundColor: '#F0FDF4',
                    borderRadius: '8px',
                    border: '1px solid #BBF7D0'
                  }}>
                    <p style={{
                      color: '#166534',
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px',
                      lineHeight: '1.5'
                    }}>
                      {selectedGap.answer}
                    </p>
                  </div>
                ) : (
                  <div style={{ position: 'relative' }}>
                    <textarea
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                      placeholder="Type your answer..."
                      style={{
                        width: '100%',
                        minHeight: '120px',
                        padding: '12px',
                        paddingRight: '44px',
                        borderRadius: '8px',
                        border: '1px solid rgba(8, 16, 40, 0.12)',
                        backgroundColor: isListening ? '#FEF2F2' : 'white',
                        fontFamily: '"Work Sans", sans-serif',
                        fontSize: '14px',
                        lineHeight: '1.5',
                        resize: 'vertical',
                        outline: 'none',
                        color: '#081028'
                      }}
                    />

                    {/* Voice button */}
                    <button
                      onClick={toggleRecording}
                      disabled={isTranscribing}
                      style={{
                        position: 'absolute',
                        right: '8px',
                        top: '8px',
                        width: '28px',
                        height: '28px',
                        borderRadius: '6px',
                        backgroundColor: isListening ? '#FEE2E2' : '#F3F4F6',
                        border: 'none',
                        cursor: isTranscribing ? 'wait' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '14px'
                      }}
                    >
                      {isTranscribing ? '...' : isListening ? '⏹' : '🎤'}
                    </button>
                  </div>
                )}

                {isListening && (
                  <p style={{
                    color: '#EF4444',
                    fontFamily: '"Work Sans", sans-serif',
                    fontSize: '12px',
                    marginTop: '8px'
                  }}>
                    Recording... click to stop
                  </p>
                )}
              </div>

              {/* Submit button */}
              {!selectedGap.answered && (
                <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(8, 16, 40, 0.06)' }}>
                  <button
                    onClick={handleAnswerQuestion}
                    disabled={!answer.trim() || submitting}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      backgroundColor: answer.trim() ? '#081028' : '#E5E7EB',
                      color: answer.trim() ? 'white' : '#9CA3AF',
                      border: 'none',
                      fontFamily: '"Work Sans", sans-serif',
                      fontSize: '14px',
                      fontWeight: 500,
                      cursor: answer.trim() ? 'pointer' : 'not-allowed'
                    }}
                  >
                    {submitting ? 'Saving...' : 'Save Answer'}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

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
                  Create an AI-powered training video from {gaps.length} knowledge gap(s) with Q&A format using Gamma AI
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
                    placeholder="e.g., Knowledge Transfer - Q&A Session"
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
                <div style={{ marginBottom: '20px' }}>
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
                    placeholder="Brief description of this knowledge transfer session..."
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

                {/* Include Answers Toggle */}
                <div style={{
                  marginBottom: '24px',
                  padding: '16px',
                  backgroundColor: '#F9FAFB',
                  borderRadius: '8px',
                  border: '1px solid #E5E7EB'
                }}>
                  <label style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    cursor: 'pointer'
                  }}>
                    <input
                      type="checkbox"
                      checked={includeAnswers}
                      onChange={e => setIncludeAnswers(e.target.checked)}
                      style={{
                        width: '18px',
                        height: '18px',
                        cursor: 'pointer'
                      }}
                    />
                    <div>
                      <p style={{
                        fontFamily: 'Inter, sans-serif',
                        fontSize: '14px',
                        fontWeight: 500,
                        color: '#081028',
                        margin: 0
                      }}>
                        Include answers in video
                      </p>
                      <p style={{
                        fontFamily: 'Inter, sans-serif',
                        fontSize: '12px',
                        color: '#6B7280',
                        margin: '4px 0 0 0'
                      }}>
                        Video will show both questions and their answers. Uncheck for questions-only format.
                      </p>
                    </div>
                  </label>
                </div>

                {/* Knowledge Gaps Summary */}
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
                    Content Summary:
                  </p>
                  <div style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '12px',
                    color: '#6B7280'
                  }}>
                    <p style={{ margin: '4px 0' }}>Total Questions: {gaps.length}</p>
                    <p style={{ margin: '4px 0' }}>Answered: {totalAnswered}</p>
                    <p style={{ margin: '4px 0' }}>Unanswered: {totalPending}</p>
                  </div>
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
                    ⚡ Gamma AI will create a Q&A format presentation with professional design and narration. This typically takes 3-5 minutes.
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
                    onClick={createTrainingVideo}
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
                  Generating Training Video...
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
