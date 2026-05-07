import { useEffect, useMemo, useState } from 'react'
import { useAppStore, type RadioSession, type RadioTrack, type Song } from '../store'

const PRESETS = [
  '深夜、轻、别太吵，适合继续工作',
  'Aimer 式的情绪，但找一点我没听过的',
  '雨天、城市、克制的 R&B 和梦幻流行',
  '粤语情绪线，安静但不要太老派',
]

const MOODS = ['深夜', '雨天', '工作', '散步', '低落', '专注']

function pct(value: number) {
  return `${Math.max(0, Math.min(100, value))}%`
}

export function RadioMode() {
  const setCurrentSong = useAppStore((s) => s.setCurrentSong)
  const setAudioUrl = useAppStore((s) => s.setAudioUrl)
  const setPlaying = useAppStore((s) => s.setPlaying)
  const sendFeedback = useAppStore((s) => s.sendFeedback)
  const [style, setStyle] = useState(PRESETS[0])
  const [mood, setMood] = useState('深夜')
  const [energy, setEnergy] = useState(42)
  const [novelty, setNovelty] = useState(55)
  const [session, setSession] = useState<RadioSession | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')

  const current = session?.queue[activeIndex] ?? session?.current ?? null
  const upcoming = session?.queue[activeIndex + 1] ?? session?.upcoming ?? null

  const visualDepth = useMemo(() => {
    if (!session) return 58
    return 62 + Math.round(novelty * 0.18)
  }, [session, novelty])

  const createSession = async (nextStyle = style) => {
    setLoading(true)
    setNotice('')
    try {
      const res = await fetch('/api/radio/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          style: nextStyle,
          mood,
          energy,
          novelty,
          voice: '克制、知性、像深夜电台',
          length: 12,
        }),
      })
      const data = await res.json()
      setSession(data)
      setActiveIndex(0)
    } catch {
      setNotice('电台生成失败，请检查后端服务')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetch('/api/radio/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        style: PRESETS[0],
        mood: '深夜',
        energy: 42,
        novelty: 55,
        voice: '克制、知性、像深夜电台',
        length: 12,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) setSession(data)
      })
      .catch(() => {
        if (!cancelled) setNotice('电台生成失败，请检查后端服务')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const playInAppleMusic = async (track: RadioTrack) => {
    try {
      const res = await fetch('/api/player/play', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: track.song.id }),
      })
      const data = await res.json()
      if (data.action === 'apple_music_play') {
        setCurrentSong(track.song)
        setAudioUrl(null)
        setPlaying(true)
        setNotice(`Apple Music 正在播放：${data.song?.title || track.song.title}`)
      } else {
        setNotice(data.error || 'Apple Music 没有找到这首歌')
      }
      sendFeedback(track.song.id, 'play_complete', 'radio_play')
    } catch {
      setNotice('Apple Music 播放失败，请检查 Music.app 自动化权限')
    }
  }

  const skipTo = (index: number) => {
    setActiveIndex(index)
  }

  const feedback = (song: Song, context: string) => {
    sendFeedback(song.id, context === 'too_much' ? 'dislike' : 'dialogue', context)
    setNotice(`已记录电台反馈：${song.title}`)
  }

  return (
    <div className="h-full overflow-y-auto radio-shell">
      <div
        className="radio-backdrop"
        style={{
          filter: `blur(${visualDepth}px)`,
          opacity: session ? 1 : 0.55,
        }}
      />

      <div className="relative z-10 p-5 space-y-4">
        <section className="radio-hero">
          <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5">
            <div className="min-w-0">
              <div className="text-[11px] uppercase font-semibold mb-3" style={{ color: 'var(--color-text-tertiary)' }}>
                Custom Radio Mode
              </div>
              <h2 className="text-3xl font-semibold leading-tight mb-3" style={{ color: 'var(--color-text-primary)' }}>
                一条按你描述生成的电台线
              </h2>
              <p className="text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--color-text-secondary)' }}>
                这里不是随机推荐。Melodia 会用你的本地口味作为锚点，再按风格、能量和新鲜度组织一条可连续播放的队列。
              </p>

              <form
                className="mt-5 space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  createSession()
                }}
              >
                <textarea
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  rows={3}
                  className="w-full radio-input text-sm"
                  placeholder="描述这个电台：比如深夜、轻、别太吵，像 Aimer 但更新一点..."
                />
                <div className="flex flex-wrap gap-2">
                  {PRESETS.map((preset) => (
                    <button
                      type="button"
                      key={preset}
                      onClick={() => {
                        setStyle(preset)
                        createSession(preset)
                      }}
                      className="radio-chip"
                    >
                      {preset}
                    </button>
                  ))}
                </div>
                <button type="submit" className="radio-primary" disabled={loading}>
                  {loading ? '生成中...' : '生成电台'}
                </button>
              </form>
            </div>

            <div className="radio-control-panel">
              <div className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
                电台参数
              </div>
              <div className="flex flex-wrap gap-2 mb-4">
                {MOODS.map((item) => (
                  <button
                    key={item}
                    onClick={() => setMood(item)}
                    className="radio-chip"
                    style={{
                      color: item === mood ? 'white' : 'var(--color-text-secondary)',
                      borderColor: item === mood ? 'var(--color-border-accent)' : 'var(--color-border-subtle)',
                    }}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <label className="radio-slider">
                <span>能量</span>
                <strong>{energy}</strong>
                <input type="range" min="0" max="100" value={energy} onChange={(e) => setEnergy(Number(e.target.value))} />
                <i style={{ width: pct(energy) }} />
              </label>
              <label className="radio-slider">
                <span>新鲜度</span>
                <strong>{novelty}</strong>
                <input type="range" min="0" max="100" value={novelty} onChange={(e) => setNovelty(Number(e.target.value))} />
                <i style={{ width: pct(novelty) }} />
              </label>
              <div className="mt-4 text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
                转场策略：Sigmoid ducking，800ms 降到 15%，DJ 后 1500ms 回升。播放由后端控制本机 Music.app。
              </div>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-4">
          <div className="radio-now">
            {current ? (
              <>
                <div className="text-[11px] uppercase font-semibold mb-4" style={{ color: 'var(--color-text-tertiary)' }}>
                  Now On Air
                </div>
                <div className="flex flex-col lg:flex-row gap-5">
                  <div className="radio-disc">
                    <div />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-3xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                      {current.song.title}
                    </div>
                    <div className="text-lg truncate mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                      {current.song.artist}
                      {current.song.album && ` · ${current.song.album}`}
                    </div>
                    <div className="radio-script mt-5">
                      {current.segue}
                    </div>
                    <div className="flex flex-wrap gap-2 mt-5">
                      <button className="radio-primary" onClick={() => playInAppleMusic(current)}>
                        后台播放
                      </button>
                      <button className="radio-secondary" onClick={() => feedback(current.song, 'more_like_this')}>
                        更像这个
                      </button>
                      <button className="radio-secondary" onClick={() => feedback(current.song, 'liked_atmosphere')}>
                        喜欢氛围
                      </button>
                      <button className="radio-secondary" onClick={() => feedback(current.song, 'too_much')}>
                        太过了
                      </button>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="discovery-empty">还没有生成电台</div>
            )}
          </div>

          <aside className="radio-next">
            <div className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
              下一段衔接
            </div>
            {upcoming ? (
              <div>
                <div className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                  {upcoming.song.title}
                </div>
                <div className="text-sm truncate mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                  {upcoming.song.artist}
                </div>
                <p className="text-sm leading-relaxed mt-4" style={{ color: 'var(--color-text-secondary)' }}>
                  {upcoming.segue}
                </p>
              </div>
            ) : (
              <div className="discovery-empty">没有下一首</div>
            )}
          </aside>
        </section>

        <section className="radio-queue">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              电台队列
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              {session?.queue.length ?? 0} tracks
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
            {(session?.queue ?? []).map((track, index) => (
              <button
                key={`${track.song.id}-${index}`}
                onClick={() => skipTo(index)}
                className="radio-queue-item"
                style={{
                  borderColor: index === activeIndex ? 'var(--color-border-accent)' : 'var(--color-border-subtle)',
                }}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{track.song.title}</strong>
                <em>{track.song.artist}</em>
              </button>
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
