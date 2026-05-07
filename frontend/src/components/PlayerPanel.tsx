import { useRef, useEffect, useState } from 'react'
import { useAppStore } from '../store'

function VinylDisc({ isPlaying, size = 120 }: { isPlaying: boolean; size?: number }) {
  return (
    <div
      className={isPlaying ? 'animate-vinyl-spin' : 'animate-vinyl-spin-paused'}
      style={{ width: size, height: size }}
    >
      <div
        className="vinyl-record w-full h-full"
        style={{
          background: `conic-gradient(
            from 0deg,
            #0a0a12,
            #16132e,
            #0a0a12,
            #16132e,
            #0a0a12,
            #16132e,
            #0a0a12
          )`,
        }}
      >
        <div className="vinyl-grooves" />
        {/* Center label with gradient */}
        <div
          className="absolute rounded-full flex items-center justify-center"
          style={{
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '35%',
            height: '35%',
            background: 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))',
            boxShadow: 'inset 0 0 0 2px rgba(255,255,255,0.1)',
          }}
        >
          <div
            className="rounded-full"
            style={{
              width: '22%',
              height: '22%',
              background: 'var(--color-bg-deep)',
              boxShadow: 'inset 0 0 2px rgba(255,255,255,0.2)',
            }}
          />
        </div>
      </div>
    </div>
  )
}

function ProgressBar() {
  const player = useAppStore((s) => s.player)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    const audio = document.querySelector('audio') as HTMLAudioElement | null
    if (!audio) return
    audioRef.current = audio

    const updateProgress = () => {
      if (audio.duration && isFinite(audio.duration)) {
        setDuration(audio.duration)
        setProgress((audio.currentTime / audio.duration) * 100)
        setCurrentTime(audio.currentTime)
      }
    }
    const updateDuration = () => {
      if (isFinite(audio.duration)) setDuration(audio.duration)
    }

    audio.addEventListener('timeupdate', updateProgress)
    audio.addEventListener('loadedmetadata', updateDuration)
    return () => {
      audio.removeEventListener('timeupdate', updateProgress)
      audio.removeEventListener('loadedmetadata', updateDuration)
    }
  }, [player.audioUrl])

  const formatTime = (seconds: number) => {
    if (!isFinite(seconds) || seconds < 0) return '0:00'
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const audio = audioRef.current
    if (!audio || !isFinite(audio.duration)) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    audio.currentTime = pct * audio.duration
  }

  return (
    <div className="space-y-1.5">
      <div className="progress-track" onClick={handleSeek}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="flex justify-between text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
        <span>
          {formatTime(currentTime)}
        </span>
        <span>{formatTime(duration)}</span>
      </div>
    </div>
  )
}

export function PlayerPanel() {
  const player = useAppStore((s) => s.player)
  const setPlaying = useAppStore((s) => s.setPlaying)
  const playNext = useAppStore((s) => s.playNext)
  const removeFromQueue = useAppStore((s) => s.removeFromQueue)
  const sendFeedback = useAppStore((s) => s.sendFeedback)

  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (player.audioUrl) {
      audio.src = player.audioUrl
      if (player.isPlaying) audio.play().catch(() => {})
    }
  }, [player.audioUrl, player.isPlaying])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (player.isPlaying) audio.play().catch(() => {})
    else audio.pause()
  }, [player.isPlaying])

  const handleEnded = () => {
    if (player.currentSong) {
      sendFeedback(player.currentSong.id, 'play_complete')
    }
    playNext()
  }

  const handleSkip = () => {
    if (player.currentSong) {
      sendFeedback(player.currentSong.id, 'skip')
    }
    playNext()
  }

  const handleFavorite = () => {
    if (player.currentSong) {
      sendFeedback(player.currentSong.id, 'favorite')
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Hidden audio element */}
      <audio ref={audioRef} onEnded={handleEnded} />

      {/* Now Playing Section */}
      <div className="shrink-0 px-5 pt-5 pb-4">
        {/* Section label */}
        <div
          className="text-[10px] font-semibold uppercase tracking-[0.15em] mb-5"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          正在播放
        </div>

        {player.currentSong ? (
          <div className="animate-fade-in-up">
            {/* Vinyl record */}
            <div className="flex justify-center mb-5">
              <div
                className={player.isPlaying ? 'animate-pulse-glow' : ''}
                style={{ borderRadius: '50%', padding: '2px' }}
              >
                <VinylDisc isPlaying={player.isPlaying} size={140} />
              </div>
            </div>

            {/* Song info */}
            <div className="text-center mb-4">
              <div
                className="text-base font-semibold truncate mb-0.5"
                style={{ color: 'var(--color-text-primary)' }}
              >
                {player.currentSong.title}
              </div>
              <div
                className="text-sm truncate"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {player.currentSong.artist}
                {player.currentSong.album && ` · ${player.currentSong.album}`}
              </div>
            </div>

            {/* Progress bar */}
            <div className="mb-4">
              <ProgressBar />
            </div>

            {/* Controls */}
            <div className="flex items-center justify-center gap-2">
              {/* Favorite */}
              <button
                onClick={handleFavorite}
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer"
                style={{ color: 'var(--color-text-tertiary)' }}
                title="收藏"
              >
                <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                </svg>
              </button>

              {/* Previous / Skip back */}
              <button
                onClick={handleSkip}
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                title="跳过"
              >
                <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
                </svg>
              </button>

              {/* Play / Pause */}
              <button
                onClick={() => setPlaying(!player.isPlaying)}
                className="w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer"
                style={{
                  background: 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))',
                  color: 'white',
                  boxShadow: '0 0 24px rgba(99,102,241,0.35)',
                }}
              >
                {player.isPlaying ? (
                  <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
                  </svg>
                ) : (
                  <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                )}
              </button>

              {/* Next / Skip forward */}
              <button
                onClick={handleSkip}
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                title="下一首"
              >
                <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
                </svg>
              </button>

              {/* Add to queue placeholder */}
              <button
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer"
                style={{ color: 'var(--color-text-tertiary)' }}
                title="队列"
              >
                <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="8" y1="6" x2="21" y2="6" />
                  <line x1="8" y1="12" x2="21" y2="12" />
                  <line x1="8" y1="18" x2="21" y2="18" />
                  <line x1="3" y1="6" x2="3.01" y2="6" />
                  <line x1="3" y1="12" x2="3.01" y2="12" />
                  <line x1="3" y1="18" x2="3.01" y2="18" />
                </svg>
              </button>
            </div>
          </div>
        ) : (
          /* No song playing */
          <div className="animate-fade-in text-center py-8">
            <div className="flex justify-center mb-5 opacity-30">
              <VinylDisc isPlaying={false} size={100} />
            </div>
            <div style={{ color: 'var(--color-text-tertiary)' }} className="text-sm">
              暂无播放
            </div>
            <div style={{ color: 'var(--color-text-tertiary)' }} className="text-xs mt-1 opacity-60">
              和 Melodia 聊聊，发现你的下一首
            </div>
          </div>
        )}
      </div>

      {/* Divider */}
      <div
        className="mx-5"
        style={{ height: 1, background: 'var(--color-border-subtle)' }}
      />

      {/* Queue Section */}
      <div className="flex-1 overflow-y-auto px-5 py-4 min-h-0">
        <div
          className="text-[10px] font-semibold uppercase tracking-[0.15em] mb-3"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          播放队列
          <span
            className="ml-1.5 inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px]"
            style={{
              background: 'var(--color-bg-glass)',
              color: 'var(--color-text-secondary)',
            }}
          >
            {player.queue.length}
          </span>
        </div>

        {player.queue.length === 0 ? (
          <div className="text-center py-6">
            <div style={{ color: 'var(--color-text-tertiary)' }} className="text-xs opacity-60">
              空队列
            </div>
          </div>
        ) : (
          <div className="space-y-0.5 stagger-children">
            {player.queue.map((song, i) => (
              <div
                key={`${song.id}-${i}`}
                className="queue-item group flex items-center gap-3 p-2.5 rounded-xl cursor-default"
              >
                <span
                  className="w-5 text-center text-[11px] font-medium shrink-0"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  {i + 1}
                </span>

                {/* Mini vinyl icon */}
                <div
                  className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
                  style={{
                    background: 'conic-gradient(from 0deg, #0a0a12, #16132e, #0a0a12, #16132e, #0a0a12)',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                  }}
                >
                  <div
                    className="rounded-full"
                    style={{
                      width: '40%',
                      height: '40%',
                      background: 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))',
                    }}
                  />
                </div>

                <div className="min-w-0 flex-1">
                  <div
                    className="text-sm truncate"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {song.title}
                  </div>
                  <div
                    className="text-xs truncate"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    {song.artist}
                  </div>
                </div>

                <button
                  onClick={() => removeFromQueue(song.id)}
                  className="p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
