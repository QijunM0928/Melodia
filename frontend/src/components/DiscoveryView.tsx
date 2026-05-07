import { useEffect, useMemo, useState } from 'react'
import { RecommendationCard } from './RecommendationCard'
import { useAppStore, type DiscoveryFeed, type Recommendation, type Song } from '../store'

const DEFAULT_PROMPTS = [
  '深夜、轻、别太吵',
  '女声、空间感、疏离',
  '像 Aimer 但更新一点',
  '安静但不要无聊',
]

const FEEDBACK_CHIPS = [
  { label: '更像这个', type: 'dialogue', context: 'more_like_this' },
  { label: '喜欢人声', type: 'dialogue', context: 'liked_vocals' },
  { label: '喜欢氛围', type: 'dialogue', context: 'liked_atmosphere' },
  { label: '太吵', type: 'dislike', context: 'too_noisy' },
]

function confidencePct(rec: Recommendation) {
  return Math.round(Math.max(0, Math.min(1, rec.confidence)) * 100)
}

export function DiscoveryView() {
  const setCurrentSong = useAppStore((s) => s.setCurrentSong)
  const setAudioUrl = useAppStore((s) => s.setAudioUrl)
  const setPlaying = useAppStore((s) => s.setPlaying)
  const sendFeedback = useAppStore((s) => s.sendFeedback)
  const [feed, setFeed] = useState<DiscoveryFeed | null>(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')

  const allRecs = useMemo(
    () => feed?.sections.flatMap((section) => section.recommendations) ?? [],
    [feed],
  )

  const loadFeed = async (nextQuery = query) => {
    setLoading(true)
    setNotice('')
    try {
      const res = await fetch('/api/discovery/feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: nextQuery.trim() }),
      })
      const data = await res.json()
      setFeed(data)
    } catch {
      setNotice('发现流加载失败，请检查后端服务')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetch('/api/discovery/feed')
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) setFeed(data)
      })
      .catch(() => {
        if (!cancelled) setNotice('发现流加载失败，请检查后端服务')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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
        if (qqWindow) qqWindow.location.href = openUrl
        else window.open(openUrl, '_blank', 'noopener,noreferrer')
        setNotice(`已打开 QQ 音乐搜索：${song.title} - ${song.artist}`)
      } else if (data.url) {
        qqWindow?.close()
        setCurrentSong(song)
        setAudioUrl(data.url)
        setPlaying(true)
        sendFeedback(song.id, 'play_complete')
      } else {
        qqWindow?.close()
        setNotice(data.error || '这首歌暂时不能播放')
      }
    } catch {
      qqWindow?.close()
      setNotice('播放失败，请检查后端服务')
    }
  }

  const handleDeepDive = (songId: number) => {
    const rec = allRecs.find((item) => item.song.id === songId)
    const nextQuery = rec ? `${rec.song.title} ${rec.song.artist} 相邻探索` : query
    setQuery(nextQuery)
    loadFeed(nextQuery)
  }

  const handleFeedback = (song: Song, type: string, context: string) => {
    sendFeedback(song.id, type, context)
    setNotice(`已记录反馈：${song.title}`)
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-5 py-4 space-y-4">
        <section className="discovery-band p-4">
          <div className="flex flex-col lg:flex-row lg:items-end gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase font-semibold mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
                Discovery Workspace
              </div>
              <h2 className="text-2xl font-semibold mb-2" style={{ color: 'var(--color-text-primary)' }}>
                今日发现流
              </h2>
              <p className="text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--color-text-secondary)' }}>
                {feed?.profile.narrative
                  ? feed.profile.narrative.slice(0, 180)
                  : '从你的本地歌单建立口味坐标，再混入 iTunes 外部候选。'}
              </p>
            </div>
            <form
              className="w-full lg:w-[420px] flex gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                loadFeed(query)
              }}
            >
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="调方向：更冷、更女声、不要太吵..."
                className="flex-1 bg-transparent px-3 py-2.5 text-sm rounded-lg"
                style={{
                  color: 'var(--color-text-primary)',
                  border: '1px solid var(--color-border-subtle)',
                  background: 'rgba(255,255,255,0.03)',
                }}
              />
              <button
                type="submit"
                className="px-3 py-2.5 rounded-lg text-sm font-medium"
                style={{
                  background: 'var(--color-indigo-light)',
                  color: 'white',
                }}
              >
                刷新
              </button>
            </form>
          </div>

          <div className="flex flex-wrap gap-2 mt-4">
            {DEFAULT_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                onClick={() => {
                  setQuery(prompt)
                  loadFeed(prompt)
                }}
                className="px-3 py-1.5 rounded-full text-xs"
                style={{
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  background: 'rgba(255,255,255,0.03)',
                }}
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
          <div className="discovery-band p-4">
            <div className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
              口味坐标
            </div>
            <div className="space-y-3">
              {(feed?.profile.dimensions ?? []).map((dim) => (
                <div key={`${dim.kind}-${dim.label}`}>
                  <div className="flex justify-between gap-3 text-xs mb-1">
                    <span className="truncate" style={{ color: 'var(--color-text-secondary)' }}>
                      {dim.label}
                    </span>
                    <span style={{ color: 'var(--color-text-tertiary)' }}>{dim.weight}%</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${dim.weight}%`,
                        background: dim.kind === 'artist' ? 'var(--color-indigo-light)' : 'var(--color-amber-warm)',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
              {feed?.profile.song_count ?? 0} 首歌构成当前画像。点击推荐卡上的反馈，会逐步改变后续方向。
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {(feed?.sections ?? []).map((section) => (
              <section key={section.id} className="discovery-column">
                <div className="px-1 mb-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                      {section.title}
                    </h3>
                    <span className="text-[10px] uppercase" style={{ color: 'var(--color-text-tertiary)' }}>
                      {section.intent}
                    </span>
                  </div>
                  <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.subtitle}
                  </p>
                </div>

                <div className="space-y-3">
                  {loading && !feed ? (
                    <div className="discovery-empty">加载发现流...</div>
                  ) : section.recommendations.length ? (
                    section.recommendations.map((rec) => (
                      <div key={`${section.id}-${rec.song.id}`} className="space-y-2">
                        <RecommendationCard rec={rec} onPlay={handlePlay} onDeepDive={handleDeepDive} />
                        <div className="flex flex-wrap gap-1.5 px-1">
                          <span className="text-[10px] px-2 py-1 rounded-full" style={{ color: 'var(--color-text-tertiary)' }}>
                            匹配 {confidencePct(rec)}%
                          </span>
                          {FEEDBACK_CHIPS.map((chip) => (
                            <button
                              key={chip.context}
                              onClick={() => handleFeedback(rec.song, chip.type, chip.context)}
                              className="text-[10px] px-2 py-1 rounded-full"
                              style={{
                                color: 'var(--color-text-secondary)',
                                border: '1px solid var(--color-border-subtle)',
                                background: 'rgba(255,255,255,0.025)',
                              }}
                            >
                              {chip.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="discovery-empty">这一栏暂时没有候选</div>
                  )}
                </div>
              </section>
            ))}
          </div>
        </section>

        {notice && (
          <div className="fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm z-50"
            style={{
              background: 'var(--color-bg-glass-strong)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {notice}
          </div>
        )}
      </div>
    </div>
  )
}
