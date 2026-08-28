import type { Block, Tag, Meta, Song, LyricsSong, Segment } from './types'

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(`${url} -> ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  meta: () => j<Meta>('/api/meta'),
  blocks: () => j<{ blocks: Block[] }>('/api/blocks').then((d) => d.blocks),
  putBlock: (id: string, ch: Record<string, unknown>) =>
    j<Block>(`/api/blocks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ch),
    }),
  revertBlock: (id: string, idx: number) =>
    j<Block>(`/api/blocks/${id}/revert/${idx}`, { method: 'POST' }),
  createBlock: (b: Partial<Block>) =>
    j<Block>('/api/blocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }),
  deleteBlock: (id: string) => j<{ deleted: string }>(`/api/blocks/${id}`, { method: 'DELETE' }),
  shift: (from: number, delta: number) =>
    j<{ shifted: number }>('/api/shift', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from, delta }),
    }),
  tags: () => j<{ tags: Tag[] }>('/api/tags').then((d) => d.tags),
  postTag: (t: Partial<Tag>) =>
    j<Tag>('/api/tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(t),
    }),
  deleteTag: (id: string) => j<{ deleted: string }>(`/api/tags/${id}`, { method: 'DELETE' }),
  putTag: (id: string, t: Partial<Tag>) =>
    j<Tag>(`/api/tags/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(t),
    }),
  setTagStatus: (id: string, status: string) =>
    j<Tag>('/api/tags/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, status }),
    }),
  gitLog: () => j<{ log: string }>('/api/git/log'),
  songs: () => j<{ songs: Song[] }>('/api/songs').then((d) => d.songs),
  lyrics: () => j<{ songs: LyricsSong[] }>('/api/lyrics').then((d) => d.songs),
  segments: () => j<{ segments: Segment[] }>('/api/segments').then((d) => d.segments),
  dtw: (sid: string) => j<{ song: string; live_t: number[]; studio_t: number[] }>(`/api/dtw/${sid}`),
}
