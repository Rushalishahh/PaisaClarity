import { useEffect, useState, useRef } from 'react'
import AppShell from '../components/AppShell'
import { api, ApiError } from '../api'

const PROMPT_SUGGESTIONS = [
  {
    title: 'Spending Summary',
    prompt: 'How much did I spend and earn recently? What is my savings rate?',
    icon: '📊',
  },
  {
    title: 'Budget Status',
    prompt: 'Am I on track with my monthly budget limit?',
    icon: '🎯',
  },
  {
    title: 'Recurring Bills',
    prompt: 'What recurring bills and subscriptions do I have coming up?',
    icon: '🔄',
  },
  {
    title: 'Account Balances',
    prompt: 'What are my verified account balances and total liquid savings?',
    icon: '🏦',
  },
  {
    title: 'Spending Forecast',
    prompt: 'What is my spending forecast for the rest of this month?',
    icon: '🔮',
  },
  {
    title: 'Goal Projection',
    prompt: 'If I want to reach a goal of 100000 saving 5000 a month, how many months will it take?',
    icon: '💡',
  },
]

export default function AiCopilot() {
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [inputPrompt, setInputPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  // Load conversation list on mount
  useEffect(() => {
    let ignore = false
    api('/ai/conversations')
      .then((data) => {
        if (!ignore) {
          setConversations(data || [])
          if (data && data.length > 0) {
            setActiveConvId(data[0].id)
          }
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load conversations')
        }
      })
    return () => {
      ignore = true
    }
  }, [])

  // Load active conversation messages
  useEffect(() => {
    if (!activeConvId) return
    let ignore = false
    api(`/ai/conversations/${activeConvId}`)
      .then((data) => {
        if (!ignore) {
          setMessages(data.messages || [])
          setError(null)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load message history')
        }
      })
    return () => {
      ignore = true
    }
  }, [activeConvId])

  async function handleSendMessage(promptToSend) {
    const text = (promptToSend || inputPrompt).trim()
    if (!text || loading) return

    setInputPrompt('')
    setError(null)

    // Optimistically show user message
    const tempUserMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMsg])
    setLoading(true)

    try {
      const res = await api('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          prompt: text,
          conversation_id: activeConvId || undefined,
        }),
      })

      const assistantMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.response,
        tool_calls: res.tool_calls || [],
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])

      // If this was a new conversation, set active ID and refresh conversation list
      if (!activeConvId && res.conversation_id) {
        setActiveConvId(res.conversation_id)
      }

      // Refresh conversations list to update titles and message counts
      api('/ai/conversations')
        .then((data) => setConversations(data || []))
        .catch(() => {})
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to get response from AI Copilot')
    } finally {
      setLoading(false)
    }
  }

  function handleNewChat() {
    setActiveConvId(null)
    setMessages([])
    setError(null)
    setInputPrompt('')
  }

  async function handleDeleteConversation(e, convId) {
    e.stopPropagation()
    if (!window.confirm('Delete this conversation history?')) return
    try {
      await api(`/ai/conversations/${convId}`, { method: 'DELETE' })
      setConversations((prev) => prev.filter((c) => c.id !== convId))
      if (activeConvId === convId) {
        handleNewChat()
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete conversation')
    }
  }

  return (
    <AppShell>
      <div className="flex h-[calc(100vh-5rem)] max-w-7xl mx-auto gap-4 p-2 sm:p-4 text-slate-100">
        {/* Sidebar for Conversation History */}
        <div
          className={`fixed inset-y-0 left-0 z-40 w-72 bg-slate-900 border-r border-slate-800 p-4 transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0 md:w-64 md:flex md:flex-col md:rounded-2xl md:border ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <span className="text-emerald-400">✨</span> Discussions
            </h2>
            <button
              onClick={() => setSidebarOpen(false)}
              className="md:hidden text-slate-400 hover:text-white text-sm px-2 py-1"
            >
              ✕
            </button>
          </div>

          <button
            onClick={() => {
              handleNewChat()
              setSidebarOpen(false)
            }}
            className="mt-4 w-full py-2.5 px-3 bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/30 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition"
          >
            <span>+</span> New Chat
          </button>

          <div className="mt-4 flex-1 overflow-y-auto space-y-1.5 pr-1">
            {conversations.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No previous chats yet.</p>
            ) : (
              conversations.map((c) => {
                const isActive = c.id === activeConvId
                return (
                  <div
                    key={c.id}
                    onClick={() => {
                      setActiveConvId(c.id)
                      setSidebarOpen(false)
                    }}
                    className={`group flex items-center justify-between p-2.5 rounded-xl text-xs cursor-pointer transition ${
                      isActive
                        ? 'bg-slate-800 text-white font-medium border border-slate-700'
                        : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                    }`}
                  >
                    <span className="truncate flex-1">{c.title || 'Conversation'}</span>
                    <button
                      onClick={(e) => handleDeleteConversation(e, c.id)}
                      title="Delete conversation"
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 px-1 ml-1 transition"
                    >
                      🗑
                    </button>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Backdrop for mobile sidebar */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/60 z-30 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Main Chat Panel */}
        <div className="flex-1 flex flex-col bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/60 backdrop-blur">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="md:hidden text-slate-400 hover:text-white p-1 rounded-lg border border-slate-700"
              >
                ☰
              </button>
              <div>
                <h1 className="text-sm sm:text-base font-semibold text-white flex items-center gap-2">
                  <span>PaisaClarity Copilot</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                    Read-Only & Secure
                  </span>
                </h1>
                <p className="text-xs text-slate-400 hidden sm:block">
                  Ask financial questions grounded directly in your recorded transactions and accounts.
                </p>
              </div>
            </div>

            <button
              onClick={handleNewChat}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 transition"
            >
              Reset Chat
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mx-4 mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex justify-between items-center">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-rose-400 hover:text-white ml-2">
                ✕
              </button>
            </div>
          )}

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center max-w-xl mx-auto text-center px-4">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-2xl mb-3">
                  🤖
                </div>
                <h3 className="text-lg font-semibold text-white mb-1">How can I assist your finances?</h3>
                <p className="text-xs text-slate-400 mb-6 max-w-md">
                  I can calculate spending summaries, check budget health, review upcoming subscriptions, track savings
                  goals, and forecast cash flow.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full text-left">
                  {PROMPT_SUGGESTIONS.map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSendMessage(item.prompt)}
                      className="p-3 rounded-xl bg-slate-800/80 hover:bg-slate-800 border border-slate-700/60 hover:border-emerald-500/30 text-left transition group"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-base">{item.icon}</span>
                        <span className="text-xs font-semibold text-white group-hover:text-emerald-300">
                          {item.title}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 line-clamp-2">{item.prompt}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => {
                const isUser = m.role === 'user'
                return (
                  <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-xs sm:text-sm leading-relaxed ${
                        isUser
                          ? 'bg-emerald-600 text-white rounded-br-none shadow-sm'
                          : 'bg-slate-800/90 text-slate-100 rounded-bl-none border border-slate-700/70 shadow-sm'
                      }`}
                    >
                      {/* Tool Calls Badges */}
                      {!isUser && m.tool_calls && m.tool_calls.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-2.5 pb-2 border-b border-slate-700/60">
                          {m.tool_calls.map((tc, idx) => (
                            <span
                              key={idx}
                              className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-emerald-300 border border-emerald-500/20 font-mono"
                            >
                              ⚡ {tc.tool_name || 'financial tool'}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="whitespace-pre-wrap">{m.content}</div>

                      <div className={`mt-1.5 text-[10px] text-right ${isUser ? 'text-emerald-200' : 'text-slate-500'}`}>
                        {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  </div>
                )
              })
            )}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-800 text-slate-400 rounded-2xl rounded-bl-none px-4 py-3 text-xs flex items-center gap-2 border border-slate-700/60">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span>Analyzing financial records...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Box */}
          <div className="p-3 border-t border-slate-800 bg-slate-900/80">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSendMessage()
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                placeholder="Ask about spending, budgets, savings goals, or recurring bills..."
                className="flex-1 bg-slate-800 border border-slate-700 text-white rounded-xl px-3.5 py-2.5 text-xs sm:text-sm focus:outline-none focus:border-emerald-500 transition placeholder:text-slate-500"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !inputPrompt.trim()}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs sm:text-sm px-4 py-2.5 rounded-xl transition flex items-center gap-1.5 shrink-0"
              >
                <span>Send</span>
                <span>➤</span>
              </button>
            </form>

            <p className="text-[10px] text-slate-500 text-center mt-2">
              PaisaClarity Copilot provides informational insights based on your records. Not certified financial advice.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
