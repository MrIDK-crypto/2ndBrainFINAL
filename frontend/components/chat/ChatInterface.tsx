'use client'

import React, { useState, useRef, useEffect, useCallback } from 'react'
import Sidebar from '../shared/Sidebar'
import Image from 'next/image'
import axios from 'axios'
import { useAuth } from '@/contexts/AuthContext'

const API_BASE = 'http://localhost:5003/api'

interface Message {
  id: string
  text: string
  isUser: boolean
  sources?: any[]
  sourceMap?: { [key: string]: { name: string; doc_id: string } }
}

interface Conversation {
  id: string
  title: string | null
  created_at: string
  updated_at: string
  last_message_at: string
  is_archived: boolean
  is_pinned: boolean
  message_count: number
}

const WelcomeCard = ({ icon, title, description, onClick }: any) => (
  <div 
    onClick={onClick}
    className="flex flex-col justify-center items-start gap-2 flex-1 px-4 py-4 rounded-xl bg-white hover:shadow-md transition-shadow cursor-pointer border border-gray-100"
  >
    <div 
      className="flex items-center justify-center rounded-lg" 
      style={{ 
        backgroundColor: '#F3F3F3',
        width: '40px',
        height: '40px'
      }}
    >
      <div style={{ width: '21.5px', height: '21.5px', flexShrink: 0 }}>
        <Image src={icon} alt={title} width={21.5} height={21.5} />
      </div>
    </div>
    <div>
      <h3 className="text-neutral-800 font-sans text-sm font-semibold mb-1">
        {title}
      </h3>
      <p className="text-gray-600 font-sans text-xs leading-tight">
        {description}
      </p>
    </div>
  </div>
)

export default function ChatInterface() {
  const { user, token, tenant, isLoading: authLoading, logout } = useAuth()
  const [activeItem, setActiveItem] = useState('ChatBot')
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Chat History State
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)

  // Auth headers for API calls
  const getAuthHeaders = () => ({
    'Authorization': token ? `Bearer ${token}` : '',
    'X-Tenant': tenant?.id || '',
    'Content-Type': 'application/json'
  })

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // Fetch chat history
  const fetchConversations = useCallback(async () => {
    if (!token) return
    setIsLoadingHistory(true)
    try {
      const response = await axios.get(`${API_BASE}/chat/conversations`, {
        headers: getAuthHeaders()
      })
      if (response.data.success) {
        setConversations(response.data.conversations || [])
      }
    } catch (error) {
      console.error('Error fetching conversations:', error)
    } finally {
      setIsLoadingHistory(false)
    }
  }, [token])

  // Load a specific conversation
  const loadConversation = async (conversationId: string) => {
    try {
      const response = await axios.get(`${API_BASE}/chat/conversations/${conversationId}`, {
        headers: getAuthHeaders()
      })
      if (response.data.success) {
        const conv = response.data.conversation
        // Convert backend messages to frontend format
        const loadedMessages: Message[] = conv.messages.map((m: any) => ({
          id: m.id,
          text: m.content,
          isUser: m.role === 'user',
          sources: m.sources || [],
        }))
        setMessages(loadedMessages)
        setCurrentConversationId(conversationId)
        setActiveTab('chat')
      }
    } catch (error) {
      console.error('Error loading conversation:', error)
    }
  }

  // Save message to current conversation
  const saveMessage = async (role: 'user' | 'assistant', content: string, sources?: any[]) => {
    if (!currentConversationId) return
    try {
      await axios.post(
        `${API_BASE}/chat/conversations/${currentConversationId}/messages`,
        { role, content, sources: sources || [] },
        { headers: getAuthHeaders() }
      )
    } catch (error) {
      console.error('Error saving message:', error)
    }
  }

  // Create new conversation
  const createNewConversation = async (): Promise<string | null> => {
    try {
      const response = await axios.post(
        `${API_BASE}/chat/conversations`,
        {},
        { headers: getAuthHeaders() }
      )
      if (response.data.success) {
        return response.data.conversation.id
      }
    } catch (error) {
      console.error('Error creating conversation:', error)
    }
    return null
  }

  // Delete conversation
  const deleteConversation = async (conversationId: string) => {
    try {
      await axios.delete(`${API_BASE}/chat/conversations/${conversationId}`, {
        headers: getAuthHeaders()
      })
      setConversations(prev => prev.filter(c => c.id !== conversationId))
      if (currentConversationId === conversationId) {
        setMessages([])
        setCurrentConversationId(null)
      }
    } catch (error) {
      console.error('Error deleting conversation:', error)
    }
  }

  // useEffect must be called before any conditional returns
  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Fetch conversations on mount and when token changes
  useEffect(() => {
    if (token) {
      fetchConversations()
    }
  }, [token, fetchConversations])

  // Handler for starting new chat
  const handleNewChat = () => {
    setMessages([])
    setCurrentConversationId(null)
  }

  // Show loading while checking auth (after all hooks)
  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-primary">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputValue,
      isUser: true,
    }

    setMessages(prev => [...prev, userMessage])
    const queryText = inputValue
    setInputValue('')
    setIsLoading(true)

    // Create new conversation if needed
    let convId = currentConversationId
    if (!convId) {
      convId = await createNewConversation()
      if (convId) {
        setCurrentConversationId(convId)
      }
    }

    // Save user message to conversation
    if (convId) {
      saveMessage('user', queryText)
    }

    try {
      // Use Enhanced RAG v2.1 endpoint with auth headers
      const response = await axios.post(`${API_BASE}/search`, {
        query: queryText,
      }, {
        headers: getAuthHeaders()
      })

      // RAG response includes answer, sources, confidence, etc.
      // Clean up the answer text - remove citation coverage and sources used lines
      let cleanedAnswer = response.data.answer || ''

      // Remove "Sources Used: [Source X, Source Y]" line
      cleanedAnswer = cleanedAnswer.replace(/Sources Used:.*$/gm, '')
      // Remove "Citation Coverage: X% of statements are cited." line
      cleanedAnswer = cleanedAnswer.replace(/.*Citation Coverage:.*$/gm, '')
      // Remove emoji lines like "📊 Citation Coverage..."
      cleanedAnswer = cleanedAnswer.replace(/^.*📊.*$/gm, '')
      cleanedAnswer = cleanedAnswer.replace(/^.*📄 Sources:.*$/gm, '')
      // Clean up extra newlines
      cleanedAnswer = cleanedAnswer.replace(/\n{3,}/g, '\n\n').trim()

      // Build source name mapping for inline citations
      const sourceMapData: { [key: string]: { name: string; doc_id: string } } = {}
      response.data.sources?.forEach((s: any, idx: number) => {
        const sourceName = s.metadata?.file_name || s.doc_id || s.chunk_id || `Source ${idx + 1}`
        const doc_id = s.doc_id || s.chunk_id || ''
        // Clean up source name - get just the filename
        const cleanName = sourceName.split('/').pop()?.replace(/^(space_msg_|File-)/, '') || sourceName
        sourceMapData[`Source ${idx + 1}`] = { name: cleanName, doc_id }
        sourceMapData[cleanName] = { name: cleanName, doc_id }
      })

      // Replace [Source X] with placeholder markers that we'll render as links
      // Use a special marker format: [[SOURCE:name:doc_id]]
      cleanedAnswer = cleanedAnswer.replace(/\[Source (\d+)\]/g, (match, num) => {
        const key = `Source ${num}`
        const source = sourceMapData[key]
        if (source) {
          return `[[SOURCE:${source.name}:${source.doc_id}]]`
        }
        return match
      })
      // Also handle [Source X, Source Y] format
      cleanedAnswer = cleanedAnswer.replace(/\[Source (\d+), Source (\d+)\]/g, (match, num1, num2) => {
        const source1 = sourceMapData[`Source ${num1}`]
        const source2 = sourceMapData[`Source ${num2}`]
        if (source1 && source2) {
          return `[[SOURCE:${source1.name}:${source1.doc_id}]], [[SOURCE:${source2.name}:${source2.doc_id}]]`
        }
        return match
      })

      const aiSources = response.data.sources?.map((s: any) => ({
        doc_id: s.doc_id || s.chunk_id,
        subject: s.metadata?.file_name || s.doc_id || s.chunk_id,
        project: s.metadata?.project || 'Unknown',
        score: s.rerank_score || s.score,
        content: s.content?.substring(0, 200) + '...'
      }))

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: cleanedAnswer,
        isUser: false,
        sources: aiSources,
        sourceMap: sourceMapData,
      }
      setMessages(prev => [...prev, aiMessage])

      // Save AI response to conversation
      if (convId) {
        saveMessage('assistant', cleanedAnswer, aiSources)
      }
    } catch (error) {
      console.error('Error:', error)
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: 'Sorry, I encountered an error. Please make sure the backend server is running on port 5003.',
        isUser: false,
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleQuickAction = (prompt: string) => {
    setInputValue(prompt)
  }

  // Render text with clickable source links
  const renderTextWithLinks = (text: string) => {
    // Split by the source markers
    const parts = text.split(/(\[\[SOURCE:[^\]]+\]\])/g)

    return parts.map((part, index) => {
      // Check if this part is a source marker
      const match = part.match(/\[\[SOURCE:([^:]+):([^\]]*)\]\]/)
      if (match) {
        const [, sourceName, docId] = match
        return (
          <a
            key={index}
            href={`${API_BASE}/document/${encodeURIComponent(docId || sourceName)}/view`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center text-blue-600 hover:text-blue-800 hover:underline font-medium"
            title={`View: ${sourceName}`}
          >
            [{sourceName}]
          </a>
        )
      }
      return <span key={index}>{part}</span>
    })
  }

  const handleFeedback = async (message: Message, rating: 'up' | 'down') => {
    try {
      await axios.post(`${API_BASE}/feedback`, {
        query: messages.find(m => m.isUser && parseInt(m.id) < parseInt(message.id))?.text || '',
        answer: message.text,
        rating: rating,
        source_ids: message.sources?.map(s => s.doc_id) || []
      }, {
        headers: getAuthHeaders()
      })
      // Visual feedback - could add toast notification here
      console.log(`Feedback recorded: ${rating}`)
    } catch (error) {
      console.error('Error submitting feedback:', error)
    }
  }

  return (
    <div className="flex h-screen bg-primary overflow-hidden">
      {/* Sidebar - Always Visible */}
      <Sidebar
        activeItem={activeItem}
        onItemClick={setActiveItem}
        conversations={conversations}
        currentConversationId={currentConversationId}
        onLoadConversation={loadConversation}
        onDeleteConversation={deleteConversation}
        onNewChat={handleNewChat}
        isLoadingHistory={isLoadingHistory}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="flex items-center px-8 py-4 bg-primary">
          {/* Left side - Chatbot title (adjust ml-X to move left/right) */}
          <div className="flex-1 flex justify-start ml-4">
            <h1 className="text-neutral-800 font-work text-xl font-semibold">
              Chatbot
            </h1>
          </div>

          {/* Right side controls */}
          <div className="flex items-center gap-4">
            {/* Search */}
            <input
              type="text"
              placeholder="Search for..."
              className="h-[42px] px-4 rounded border border-neutral-500 bg-secondary text-sm outline-none"
              style={{ width: '352px' }}
            />

            {/* New Chat Button */}
            <button
              onClick={handleNewChat}
              className="flex items-center justify-center gap-3 px-4 h-[42px] rounded bg-secondary hover:bg-opacity-80 transition-colors whitespace-nowrap"
            >
              <span className="text-neutral-800 font-sans text-sm font-medium">
                New Chat
              </span>
            </button>

            {/* User info and logout */}
            <div className="flex items-center gap-3">
              <span className="text-neutral-600 font-sans text-sm">
                {tenant?.name?.toUpperCase()}
              </span>
              <button
                onClick={logout}
                className="flex items-center justify-center gap-2 px-3 h-[42px] rounded bg-gray-200 hover:bg-gray-300 transition-colors"
              >
                <span className="text-neutral-800 font-sans text-sm font-medium">
                  Logout
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 flex items-center justify-center px-8 py-4 overflow-hidden">
          <div
            className="flex flex-col justify-end items-center gap-5 bg-secondary rounded-3xl shadow-sm p-5 h-full max-h-[calc(100vh-120px)] w-full"
            style={{ maxWidth: '1000px' }}
          >
            {/* Messages or Welcome Screen */}
            {messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-6 w-full overflow-auto">
                <div className="text-center">
                  <div className="w-20 h-20 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 mx-auto mb-3 overflow-hidden">
                    <Image src="/Maya.png" alt="Rishit" width={80} height={80} />
                  </div>
                  <h2 className="text-neutral-800 font-work text-2xl font-semibold mb-2">
                    Welcome, {user?.name?.split(' ')[0] || 'User'}
                  </h2>
                  <p className="text-gray-600 font-sans text-sm">
                    Start by scripting a task, and let the chat take over.
                  </p>
                  <p className="text-gray-500 font-sans text-xs">
                    Not sure where to start?
                  </p>
                </div>

                {/* Quick Actions Grid */}
                <div className="grid grid-cols-3 gap-3 w-full max-w-3xl px-4">
                  <WelcomeCard
                    icon="/Project.svg"
                    title="Summarize Research"
                    description="Derive highlights from past partnerships."
                    onClick={() => handleQuickAction("Summarize ... research for me")}
                  />
                  <WelcomeCard
                    icon="/PPT.svg"
                    title="PPT Generation"
                    description="Design custom visuals with AI."
                    onClick={() => handleQuickAction("Generate a presentation for the Brooklyn Navy Yard project")}
                  />
                  <WelcomeCard
                    icon="/Research.svg"
                    title="Research"
                    description="Quickly gather and summarize info."
                    onClick={() => handleQuickAction("What were the key challenges in the Southeast projects?")}
                  />
                  <WelcomeCard
                    icon="/Article.svg"
                    title="Generate Article"
                    description="Write articles on any topic instantly."
                    onClick={() => handleQuickAction("Tell me about market-to-market issues")}
                  />
                  <WelcomeCard
                    icon="/Data.svg"
                    title="Data Analytics"
                    description="Analyze data with AI-driven insights."
                    onClick={() => handleQuickAction("Analyze the NYISO bidding data")}
                  />
                  <WelcomeCard
                    icon="/Code.svg"
                    title="Code Explainer"
                    description="Explain code accurately & quickly."
                    onClick={() => handleQuickAction("Who was involved in the Fundamentals Meetings?")}
                  />
                </div>
              </div>
            ) : (
              <div className="flex-1 w-full overflow-y-auto px-4 space-y-4 scrollbar-thin">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`px-6 py-4 rounded-2xl ${
                        message.isUser
                          ? 'bg-white text-neutral-800 shadow-sm max-w-[50%]'
                          : 'bg-transparent text-neutral-800 max-w-[70%]'
                      }`}
                    >
                      <div className="font-sans text-[15px] leading-relaxed whitespace-pre-wrap">
                        {renderTextWithLinks(message.text)}
                      </div>
                      
                      {message.sources && message.sources.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {message.sources.slice(0, 5).map((source, idx) => (
                            <div key={idx} className="group relative inline-block">
                              <a
                                href={`${API_BASE}/document/${encodeURIComponent(source.doc_id || source.subject)}/view`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-gray-100 hover:bg-gray-200 text-xs text-gray-600 hover:text-gray-800 transition-colors cursor-pointer"
                              >
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                                <span className="max-w-[120px] truncate">{source.subject?.split('/').pop() || source.subject}</span>
                              </a>
                              {/* Tooltip on hover */}
                              <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block z-10">
                                <div className="bg-gray-800 text-white text-xs rounded-lg px-3 py-2 max-w-[250px] shadow-lg">
                                  <p className="font-medium mb-1">{source.subject}</p>
                                  <p className="text-gray-300 text-[10px]">{source.project}</p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Feedback buttons for AI responses */}
                      {!message.isUser && (
                        <div className="mt-2 flex items-center gap-1 pt-2">
                          <button
                            onClick={() => handleFeedback(message, 'up')}
                            className="p-1.5 hover:bg-gray-100 rounded-full text-gray-400 hover:text-gray-600 transition-colors"
                            title="Good answer"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleFeedback(message, 'down')}
                            className="p-1.5 hover:bg-gray-100 rounded-full text-gray-400 hover:text-gray-600 transition-colors"
                            title="Poor answer"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" />
                            </svg>
                          </button>
                          <button
                            className="p-1.5 hover:bg-gray-100 rounded-full text-gray-400 hover:text-gray-600 transition-colors ml-1"
                            title="Copy response"
                            onClick={() => navigator.clipboard.writeText(message.text)}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-transparent px-6 py-4 rounded-2xl">
                      <div className="flex gap-2">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      </div>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>
            )}

            {/* Input Box */}
            <div 
              className="flex flex-col justify-between items-start self-stretch bg-white rounded-[20px] border border-gray-200 p-4"
              style={{ height: '79px' }}
            >
              <div className="flex items-center gap-3 w-full">
                <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                  <Image src="/attach.svg" alt="Attach" width={20} height={20} />
                </button>

                <input
                  type="text"
                  placeholder="Write your message ..."
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                  className="flex-1 outline-none text-gray-700 font-sans text-[15px]"
                />

                <button 
                  onClick={handleSend}
                  disabled={isLoading || !inputValue.trim()}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Image src="/send.svg" alt="Send" width={20} height={20} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
