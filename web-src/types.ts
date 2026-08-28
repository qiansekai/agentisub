export interface Block {
  id: string
  start: number
  end: number
  kind: string
  song: string
  ja: string
  zh: string
  confidence: string
  evidence: { method: string; detail: string }
  tags: string[]
  history: HistoryEntry[]
  locked: boolean
}

export interface HistoryEntry {
  actor: string
  ts: string
  before?: Record<string, unknown>
  after?: Record<string, unknown>
  reply?: string
  patch_id?: string
}

export interface Tag {
  id: string
  type: string
  note: string
  block_id?: string
  start?: number
  end?: number
  status: string
  reply?: string
  created: string
}

export interface Meta {
  total: number
  green: number
  yellow: number
  red: number
  tags_open: number
}

export interface Song {
  id: string
  title: string
  t0: number
  t1: number
  blocks: number
  green: number
  yellow: number
  red: number
}

export interface LyricsSong {
  id: string
  netease_id: number
  title: string
  lines: string[]
  lines_zh?: string[]
  lines_roma?: string[]
}

export interface Segment {
  type: string
  t0: number
  t1: number
  label?: string
  song_id?: string
  title?: string
  green?: number
  yellow?: number
  red?: number
  blocks?: number
  outfit?: string
  guest?: string
  encore?: boolean
  no_official?: boolean
}

export const TAG_TYPES: Record<string, string> = {
  retime: '🕐 轴不准',
  relisten: '👂 需重听',
  retranslate: '🌐 翻译差',
  lyrics: '🎵 缺歌词',
  text: '📝 文本可疑',
  split: '✂️ 拆/合句',
  confirm: '✅ 已确认',
}

export const CONF_COLORS: Record<string, string> = {
  green: '#4caf50',
  yellow: '#ffc107',
  red: '#f44336',
  gray: '#9e9e9e',
}
