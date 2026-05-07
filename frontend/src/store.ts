import { create } from 'zustand'

export interface Song {
  id: number
  title: string
  artist: string
  album: string
  genres?: string[]
  tags?: string[]
  duration_ms?: number
}

export interface Recommendation {
  song: Song
  reason: string
  confidence: number
  is_exploratory: boolean
  matched_dimensions: string[]
}

export interface TasteDimension {
  label: string
  kind: string
  weight: number
}

export interface DiscoverySection {
  id: string
  title: string
  subtitle: string
  intent: string
  recommendations: Recommendation[]
}

export interface DiscoveryFeed {
  query: string
  profile: {
    song_count: number
    narrative: string
    dimensions: TasteDimension[]
  }
  sections: DiscoverySection[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  recommendations?: Recommendation[]
  timestamp: number
}

export interface PlayerState {
  currentSong: Song | null
  isPlaying: boolean
  audioUrl: string | null
  queue: Song[]
  playCount: number
}

export interface AppState {
  // Chat
  messages: ChatMessage[]
  isLoading: boolean
  addMessage: (msg: ChatMessage) => void
  setLoading: (v: boolean) => void

  // Player
  player: PlayerState
  setCurrentSong: (song: Song | null) => void
  setPlaying: (v: boolean) => void
  setAudioUrl: (url: string | null) => void
  addToQueue: (songs: Song[]) => void
  removeFromQueue: (id: number) => void
  playNext: () => void

  // Feedback
  sendFeedback: (songId: number, type: string, context?: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  // Chat
  messages: [],
  isLoading: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setLoading: (v) => set({ isLoading: v }),

  // Player
  player: {
    currentSong: null,
    isPlaying: false,
    audioUrl: null,
    queue: [],
    playCount: 0,
  },
  setCurrentSong: (song) =>
    set((s) => ({ player: { ...s.player, currentSong: song } })),
  setPlaying: (v) =>
    set((s) => ({ player: { ...s.player, isPlaying: v } })),
  setAudioUrl: (url) =>
    set((s) => ({ player: { ...s.player, audioUrl: url } })),
  addToQueue: (songs) =>
    set((s) => ({ player: { ...s.player, queue: [...s.player.queue, ...songs] } })),
  removeFromQueue: (id) =>
    set((s) => ({
      player: { ...s.player, queue: s.player.queue.filter((s) => s.id !== id) },
    })),
  playNext: () =>
    set((s) => {
      const [next, ...rest] = s.player.queue
      return {
        player: {
          ...s.player,
          currentSong: next || null,
          queue: rest,
          isPlaying: !!next,
        },
      }
    }),

  // Feedback
  sendFeedback: async (songId, type, context = '') => {
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, feedback_type: type, context }),
      })
    } catch {
      // Feedback is best-effort; playback and chat should not fail if logging fails.
    }
  },
}))
