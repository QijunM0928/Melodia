import { useAppStore, type Recommendation, type Song } from '../store'

interface Props {
  rec: Recommendation
  onPlay: (song: Song) => void
  onDeepDive: (songId: number) => void
}

export function RecommendationCard({ rec, onPlay, onDeepDive }: Props) {
  const sendFeedback = useAppStore((s) => s.sendFeedback)
  const addToQueue = useAppStore((s) => s.addToQueue)
  const isExternal = rec.song.tags?.includes('iTunes') ?? false
  const opensQQ = rec.song.id <= 0

  return (
    <div
      className="card-lift rounded-xl overflow-hidden"
      style={{
        background: 'var(--color-bg-glass)',
        border: '1px solid var(--color-border-subtle)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div className="flex gap-3 p-3">
        {/* Vinyl record thumbnail */}
        <div className="shrink-0 self-center">
          <div
            className="w-12 h-12 rounded-full relative"
            style={{
              background: `conic-gradient(
                from 0deg,
                #0a0a12,
                #16132e,
                #0a0a12,
                #16132e,
                #0a0a12
              )`,
              boxShadow: '0 2px 12px rgba(0,0,0,0.4), inset 0 0 0 1px rgba(255,255,255,0.05)',
            }}
          >
            {/* Grooves */}
            <div
              className="absolute inset-0 rounded-full"
              style={{
                background: 'repeating-radial-gradient(circle at center, transparent 0px, transparent 2px, rgba(255,255,255,0.012) 2px, rgba(255,255,255,0.012) 3px)',
              }}
            />
            {/* Center label */}
            <div
              className="absolute rounded-full flex items-center justify-center"
              style={{
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: '38%',
                height: '38%',
                background: rec.is_exploratory
                  ? 'linear-gradient(135deg, #92400e, #f59e0b)'
                  : 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-indigo-light))',
                boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)',
              }}
            >
              <div
                className="rounded-full"
                style={{
                  width: '24%',
                  height: '24%',
                  background: 'var(--color-bg-deep)',
                }}
              />
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 py-0.5">
          <div className="flex items-center gap-2 mb-0.5">
            <span
              className="font-medium text-sm truncate"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {rec.song.title}
            </span>
            {rec.is_exploratory && (
              <span
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
                style={{
                  background: 'rgba(245,158,11,0.15)',
                  color: 'var(--color-amber-warm)',
                  border: '1px solid rgba(245,158,11,0.2)',
                }}
              >
                探索
              </span>
            )}
            {isExternal && (
              <span
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
                style={{
                  background: 'rgba(20,184,166,0.14)',
                  color: '#5eead4',
                  border: '1px solid rgba(20,184,166,0.22)',
                }}
              >
                外部发现
              </span>
            )}
          </div>
          <div
            className="text-xs truncate mb-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {rec.song.artist}
            {rec.song.album && ` · ${rec.song.album}`}
          </div>
          <div
            className="text-xs leading-relaxed line-clamp-2 mb-1.5"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {rec.reason}
          </div>

          {/* Matched dimensions */}
          {rec.matched_dimensions.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {rec.matched_dimensions.map((d) => (
                <span
                  key={d}
                  className="text-[10px] px-1.5 py-0.5 rounded-full"
                  style={{
                    background: 'rgba(99,102,241,0.12)',
                    color: 'var(--color-text-accent)',
                    border: '1px solid rgba(99,102,241,0.15)',
                  }}
                >
                  {d}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div
        className="flex items-center gap-0.5 px-2 py-1.5"
        style={{ borderTop: '1px solid var(--color-border-subtle)' }}
      >
        {/* Play */}
        <button
          onClick={() => onPlay(rec.song)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-all duration-200 cursor-pointer"
          style={{
            color: 'var(--color-text-accent)',
            cursor: 'pointer',
          }}
          title={opensQQ ? '用 QQ 音乐搜索并播放' : '播放'}
        >
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24">
            <path d="M8 5v14l11-7z" />
          </svg>
          {opensQQ ? 'QQ音乐' : '播放'}
        </button>

        {/* Add to queue */}
        <button
          onClick={() => addToQueue([rec.song])}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-all duration-200 cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          加入队列
        </button>

        {/* Deep dive */}
        <button
          onClick={() => onDeepDive(rec.song.id)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-all duration-200 cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 14h4v6M20 10h-4V4M4.5 14.5L9 10M19.5 9.5L15 14" />
          </svg>
          深挖
        </button>

        <div className="flex-1" />

        {/* Favorite */}
        <button
          onClick={() => sendFeedback(rec.song.id, 'favorite')}
          className="p-1.5 rounded-lg transition-all duration-200 cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
          title="收藏"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
          </svg>
        </button>

        {/* Skip */}
        <button
          onClick={() => sendFeedback(rec.song.id, 'skip')}
          className="p-1.5 rounded-lg transition-all duration-200 cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
          title="跳过"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  )
}
