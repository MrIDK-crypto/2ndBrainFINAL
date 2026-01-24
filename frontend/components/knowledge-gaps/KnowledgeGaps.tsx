'use client'

import React, { useState, useEffect, useRef } from 'react'
import Sidebar from '../shared/Sidebar'
import axios from 'axios'
import { useAuth, useAuthHeaders } from '@/contexts/AuthContext'

const API_BASE = 'http://localhost:5003/api'
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
    </div>
  )
}
