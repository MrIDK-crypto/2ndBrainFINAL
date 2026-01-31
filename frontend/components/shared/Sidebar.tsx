'use client'

import React, { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

interface ChatConversation {
  id: string
  title: string | null
  last_message_at: string
  message_count: number
}

interface SidebarProps {
  activeItem?: string
  onItemClick?: (item: string) => void
  // Chat History Props
  conversations?: ChatConversation[]
  currentConversationId?: string | null
  onLoadConversation?: (id: string) => void
  onDeleteConversation?: (id: string) => void
  onNewChat?: () => void
  isLoadingHistory?: boolean
}

export default function Sidebar({
  activeItem = 'ChatBot',
  onItemClick,
  conversations = [],
  currentConversationId,
  onLoadConversation,
  onDeleteConversation,
  onNewChat,
  isLoadingHistory = false
}: SidebarProps) {
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(true)

  const handleClick = (item: string) => {
    if (onItemClick) {
      onItemClick(item)
    }
  }

  // Format relative time
  const formatRelativeTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m`
    if (diffHours < 24) return `${diffHours}h`
    if (diffDays < 7) return `${diffDays}d`
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const showChatHistory = activeItem === 'ChatBot' && (conversations.length > 0 || onNewChat)

  return (
    <div
      className="h-full flex flex-col py-6"
      style={{ width: '280px', backgroundColor: '#FFE2BF' }}
    >
      <div className="px-6">
        {/* Logo */}
        <div className="mb-8">
          <Link href="/">
            <div className="flex items-center gap-3 cursor-pointer">
              <div style={{ width: '41px', height: '51px', aspectRatio: '41/51' }}>
                <Image 
                  src="/owl.png" 
                  alt="2nd Brain Logo" 
                  width={41} 
                  height={51}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              </div>
              <h1
                style={{
                  color: '#081028',
                  fontFamily: '"Work Sans", sans-serif',
                  fontSize: '20px',
                  fontWeight: 600,
                  lineHeight: '22px',
                  whiteSpace: 'nowrap'
                }}
              >
                2nd Brain
              </h1>
            </div>
          </Link>
        </div>

        {/* Search */}
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search for..."
            className="w-full h-[42px] px-4 rounded bg-primary border border-border text-sm outline-none"
          />
        </div>

        {/* Menu Items */}
        <div className="space-y-1">
          <Link href="/integrations">
            <div
              onClick={() => handleClick('Integrations')}
              className={`flex items-center gap-3 px-4 py-3 rounded cursor-pointer transition-colors ${
                activeItem === 'Integrations' ? 'bg-[#FFE2BF]' : 'hover:bg-secondary'
              }`}
            >
              <div style={{ width: '14px', height: '14px', flexShrink: 0 }}>
                <Image src="/Integrations.png" alt="Integrations" width={14} height={14} />
              </div>
              <span className="text-neutral-800 text-sm font-medium font-sans">
                Integrations
              </span>
            </div>
          </Link>

          <Link href="/documents">
            <div
              onClick={() => handleClick('Documents')}
              className={`flex items-center gap-3 px-4 py-3 rounded cursor-pointer transition-colors ${
                activeItem === 'Documents' ? 'bg-[#FFE2BF]' : 'hover:bg-secondary'
              }`}
            >
              <div style={{ width: '14px', height: '14px', flexShrink: 0 }}>
                <Image src="/documents.png" alt="Documents" width={14} height={14} />
              </div>
              <span className="text-neutral-800 text-sm font-medium font-sans">
                Documents
              </span>
            </div>
          </Link>

          <Link href="/knowledge-gaps">
            <div
              onClick={() => handleClick('Knowledge Gaps')}
              className={`flex items-center gap-3 px-4 py-3 rounded cursor-pointer transition-colors ${
                activeItem === 'Knowledge Gaps' ? 'bg-[#FFE2BF]' : 'hover:bg-secondary'
              }`}
            >
              <div style={{ width: '14px', height: '14px', flexShrink: 0 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M7 1C3.686 1 1 3.686 1 7s2.686 6 6 6 6-2.686 6-6-2.686-6-6-6zm0 10.5a.75.75 0 110-1.5.75.75 0 010 1.5zm.75-3a.75.75 0 01-1.5 0V5.75a.75.75 0 011.5 0V8.5z" fill="#081028"/>
                </svg>
              </div>
              <span className="text-neutral-800 text-sm font-medium font-sans">
                Knowledge Gaps
              </span>
            </div>
          </Link>

          <Link href="/">
            <div
              onClick={() => handleClick('ChatBot')}
              className={`flex items-center gap-3 px-4 py-3 rounded cursor-pointer transition-colors ${
                activeItem === 'ChatBot' ? 'bg-[#FFE2BF]' : 'hover:bg-secondary'
              }`}
            >
              <div style={{ width: '14px', height: '14px', flexShrink: 0 }}>
                <Image src="/Chatbot.png" alt="ChatBot" width={14} height={14} />
              </div>
              <span className="text-neutral-800 text-sm font-medium font-sans">
                ChatBot
              </span>
            </div>
          </Link>

          <Link href="/training-guides">
            <div
              onClick={() => handleClick('Training Guides')}
              className={`flex items-center gap-3 px-4 py-3 rounded cursor-pointer transition-colors ${
                activeItem === 'Training Guides' ? 'bg-[#FFE2BF]' : 'hover:bg-secondary'
              }`}
            >
              <div style={{ width: '14px', height: '14px', flexShrink: 0 }}>
                <Image src="/Training.png" alt="Training" width={14} height={14} />
              </div>
              <span className="text-neutral-800 text-sm font-medium font-sans">
                Training Guides
              </span>
            </div>
          </Link>
        </div>

        {/* Chat History Section - Only show on ChatBot page */}
        {showChatHistory && (
          <div className="mt-6">
            {/* Section Header */}
            <div className="flex items-center justify-between px-4 mb-2">
              <button
                onClick={() => setIsHistoryExpanded(!isHistoryExpanded)}
                className="flex items-center gap-2 text-xs font-medium text-gray-500 uppercase tracking-wide hover:text-gray-700 transition-colors"
              >
                <svg
                  className={`w-3 h-3 transition-transform ${isHistoryExpanded ? 'rotate-90' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                Chat History
              </button>
              {onNewChat && (
                <button
                  onClick={onNewChat}
                  className="p-1 text-gray-400 hover:text-gray-600 hover:bg-secondary rounded transition-colors"
                  title="New Chat"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
              )}
            </div>

            {/* Conversation List */}
            {isHistoryExpanded && (
              <div className="space-y-0.5 max-h-[280px] overflow-y-auto scrollbar-thin">
                {isLoadingHistory ? (
                  <div className="flex items-center justify-center py-4">
                    <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></div>
                  </div>
                ) : conversations.length === 0 ? (
                  <div className="px-4 py-3 text-center">
                    <p className="text-xs text-gray-400">No chat history yet</p>
                  </div>
                ) : (
                  conversations.slice(0, 10).map((conv) => (
                    <div
                      key={conv.id}
                      onClick={() => onLoadConversation?.(conv.id)}
                      className={`group flex items-center gap-2 px-4 py-2 cursor-pointer transition-colors ${
                        currentConversationId === conv.id
                          ? 'bg-[#FFE2BF]'
                          : 'hover:bg-secondary'
                      }`}
                    >
                      {/* Chat Icon */}
                      <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>

                      {/* Title */}
                      <span className="flex-1 text-sm text-neutral-700 truncate">
                        {conv.title || 'Untitled'}
                      </span>

                      {/* Time */}
                      <span className="text-[10px] text-gray-400 flex-shrink-0 group-hover:hidden">
                        {formatRelativeTime(conv.last_message_at)}
                      </span>

                      {/* Delete button - show on hover */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          if (confirm('Delete this conversation?')) {
                            onDeleteConversation?.(conv.id)
                          }
                        }}
                        className="hidden group-hover:block p-0.5 text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                        title="Delete"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1"></div>

      {/* User Profile at Bottom */}
      <div className="px-6 space-y-1">
        {/* User Profile */}
        <div className="flex items-center gap-3 px-4 py-3 mt-4">
          <div className="w-10 h-10 rounded-full overflow-hidden flex-shrink-0">
            <Image src="/Maya.png" alt="Rishit" width={40} height={40} />
          </div>
          <div>
            <div className="text-neutral-800 text-sm font-medium">Rishit</div>
            <div className="text-gray-500 text-xs">Account settings</div>
          </div>
        </div>
      </div>
    </div>
  )
}
