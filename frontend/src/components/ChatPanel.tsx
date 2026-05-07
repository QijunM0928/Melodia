import { useRef, useEffect, useState } from 'react'
import { useAppStore, type ChatMessage, type Song } from '../store'
import { RecommendationCard } from './RecommendationCard'

const SUGGESTIONS = [
  '适合深夜发呆的氛围',
  '来点有攻击性的',
  '推荐跟这首歌类似的',
  '别推电子的了',
]

export function ChatPanel() {
  const messages = useAppStore((s) => s.messages)
  const isLoading = useAppStore((s) => s.isLoading)
  const addMessage = useAppStore((s) => s.addMessage)
  const setLoading = useAppStore((s) => s.setLoading)
  const setCurrentSong = useAppStore((s) => s.setCurrentSong)
  const setAudioUrl = useAppStore((s) => s.setAudioUrl)
  const setPlaying = useAppStore((s) => s.setPlaying)
  const sendFeedback = useAppStore((s) => s.sendFeedback)

  const inputRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [inputValue, setInputValue] = useState('')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      timestamp: 0,
    }
    addMessage(userMsg)
    setLoading(true)
    setInputValue('')

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text.trim() }),
      })
      const data = await res.json()

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.response || '抱歉，出了点问题',
        recommendations: data.recommendations,
        timestamp: 0,
      }
      addMessage(assistantMsg)
    } catch {
      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '连接失败，请检查后端是否运行',
        timestamp: 0,
      })
    } finally {
      setLoading(false)
    }
  }

  const handlePlay = async (song: Song) => {
    const qqWindow = song.id <= 0 ? window.open('about:blank', '_blank') : null
    try {
      const res = await fetch('/api/player/play', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: song.id }),
      })
      const data = await res.json()
      const openUrl = data.open_url || data.url
      if (data.action === 'open_url' && openUrl) {
        if (qqWindow) {
          qqWindow.location.href = openUrl
        } else {
          window.open(openUrl, '_blank', 'noopener,noreferrer')
        }
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `已打开 QQ 音乐搜索：${song.title} - ${song.artist}`,
          timestamp: 0,
        })
      } else if (data.url) {
        setCurrentSong(song)
        setAudioUrl(data.url)
        setPlaying(true)
        sendFeedback(song.id, 'play_complete')
      } else {
        qqWindow?.close()
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.error || '这首歌暂时不能播放，需要先完成网易云匹配',
          timestamp: 0,
        })
      }
    } catch {
      qqWindow?.close()
      setPlaying(false)
      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '播放失败，请检查后端服务',
        timestamp: 0,
      })
    }
  }

  const handleDeepDive = async (songId: number) => {
    await sendMessage(`帮我深挖一下这首歌 ${songId}`)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputValue.trim()) {
      sendMessage(inputValue)
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: isEmpty ? '0' : '24px' }}
      >
        {isEmpty ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center h-full px-6">
            <div className="animate-fade-in-up text-center max-w-md">
              {/* Decorative music icon */}
              <div
                className="w-20 h-20 mx-auto mb-6 rounded-2xl flex items-center justify-center"
                style={{
                  background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(245,158,11,0.15))',
                  border: '1px solid rgba(99,102,241,0.15)',
                }}
              >
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 18V5l12-2v13" />
                  <circle cx="6" cy="18" r="3" />
                  <circle cx="18" cy="16" r="3" />
                </svg>
              </div>

              <h2
                className="text-2xl font-semibold mb-2"
                style={{ color: 'var(--color-text-primary)' }}
              >
                想听点什么？
              </h2>
              <p
                className="text-sm leading-relaxed mb-8"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                告诉我你想听什么，或者描述一种氛围<br />
                我会为你找到最合适的音乐
              </p>

              {/* Suggestion chips */}
              <div className="flex flex-wrap justify-center gap-2 stagger-children">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="suggestion-chip glass rounded-full px-4 py-2 text-sm cursor-pointer"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Message list */
          <div className="space-y-5">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                style={{ animationDelay: '0ms' }}
              >
                <div
                  className={`max-w-[85%] ${
                    msg.role === 'user' ? 'animate-slide-right' : 'animate-slide-left'
                  }`}
                >
                  {/* Avatar + bubble */}
                  <div className={`flex items-end gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                    {/* Avatar */}
                    <div
                      className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-medium"
                      style={{
                        background: msg.role === 'user'
                          ? 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))'
                          : 'linear-gradient(135deg, var(--color-amber-warm), var(--color-rose-accent))',
                        color: 'white',
                      }}
                    >
                      {msg.role === 'user' ? '你' : 'M'}
                    </div>

                    {/* Bubble */}
                    <div
                      className={`rounded-2xl px-4 py-3 msg-${msg.role}`}
                      style={{
                        background: msg.role === 'user'
                          ? 'linear-gradient(135deg, var(--color-indigo-mid), rgba(99,102,241,0.8))'
                          : 'var(--color-bg-glass-strong)',
                        border: msg.role === 'assistant' ? '1px solid var(--color-border-subtle)' : 'none',
                        backdropFilter: msg.role === 'assistant' ? 'blur(12px)' : 'none',
                        color: msg.role === 'user' ? '#fff' : 'var(--color-text-primary)',
                      }}
                    >
                      <div className="whitespace-pre-wrap text-sm leading-relaxed">
                        {msg.content}
                      </div>

                      {/* Recommendations */}
                      {msg.recommendations && msg.recommendations.length > 0 && (
                        <div className="mt-3 space-y-2.5 stagger-children">
                          {msg.recommendations.map((rec) => (
                            <RecommendationCard
                              key={rec.song.id}
                              rec={rec}
                              onPlay={handlePlay}
                              onDeepDive={handleDeepDive}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="flex justify-start animate-fade-in">
                <div className="flex items-end gap-2.5">
                  <div
                    className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-medium"
                    style={{
                      background: 'linear-gradient(135deg, var(--color-amber-warm), var(--color-rose-accent))',
                      color: 'white',
                    }}
                  >
                    M
                  </div>
                  <div
                    className="rounded-2xl rounded-bl px-4 py-3 msg-assistant"
                    style={{
                      background: 'var(--color-bg-glass-strong)',
                      border: '1px solid var(--color-border-subtle)',
                      backdropFilter: 'blur(12px)',
                    }}
                  >
                    <div className="flex gap-2">
                      {[0, 1, 2].map((i) => (
                        <div
                          key={i}
                          className="w-2 h-2 rounded-full"
                          style={{
                            background: 'var(--color-text-accent)',
                            animation: 'dotPulse 1.4s ease-in-out infinite',
                            animationDelay: `${i * 200}ms`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div
        className="shrink-0 px-5 py-4"
        style={{
          background: 'linear-gradient(to top, var(--color-bg-deep) 60%, transparent)',
        }}
      >
        <form onSubmit={handleSubmit} className="flex gap-2.5 items-center">
          <div
            className="flex-1 flex items-center glass rounded-2xl overflow-hidden"
            style={{ borderColor: 'var(--color-border-subtle)' }}
          >
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="描述你想听的音乐..."
              disabled={isLoading}
              className="flex-1 bg-transparent px-4 py-3 text-sm focus:outline-none"
              style={{
                color: 'var(--color-text-primary)',
              }}
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !inputValue.trim()}
            className="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer"
            style={{
              background: inputValue.trim()
                ? 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))'
                : 'var(--color-bg-glass)',
              border: '1px solid var(--color-border-subtle)',
              boxShadow: inputValue.trim() ? '0 0 20px rgba(99,102,241,0.3)' : 'none',
              color: inputValue.trim() ? 'white' : 'var(--color-text-tertiary)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  )
}
