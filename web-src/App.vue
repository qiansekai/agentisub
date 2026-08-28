<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { api } from './api'
import type { Block, Tag, Meta, Song, LyricsSong, Segment } from './types'
import { TAG_TYPES } from './types'
import TimelineCanvas from './components/TimelineCanvas.vue'
import BlockPanel from './components/BlockPanel.vue'
import TagDialog from './components/TagDialog.vue'
import DiffPanel from './components/DiffPanel.vue'
import LiveLyrics from './components/LiveLyrics.vue'
import type { LiveLyricSong } from './components/LiveLyrics.vue'

const meta = ref<Meta>({ total: 0, green: 0, yellow: 0, red: 0, tags_open: 0 })
const blocks = ref<Block[]>([])
const tags = ref<Tag[]>([])
const songs = ref<Song[]>([])
const lyrics = ref<LyricsSong[]>([])
const lyricsLive = ref<LiveLyricSong[]>([])
const segments = ref<Segment[]>([])
const dtwMap = ref<{ song: string; live_t: number[]; studio_t: number[] } | null>(null)
const showDtw = ref(false)
const peaks = ref<Int16Array | null>(null)
const spectrum = ref<Uint8Array | null>(null)
const spectrumMeta = ref<{ fps: number; bands: number; frames: number } | null>(null)
const currentTime = ref(0)
const pxPerSec = ref(20)
const selected = ref<Block | null>(null)
const showSpectrum = ref(false)
const tagDialog = ref(false)
const tagRange = ref<{ start: number; end: number; block_id?: string } | null>(null)
const bulkBlocks = ref<string[]>([])
const editingTag = ref<Tag | null>(null)
const drawer = ref(true)
const gitLog = ref('')
const gitDialog = ref(false)
const diffDialog = ref(false)
const video = ref<HTMLVideoElement | null>(null)
const duration = ref(14571.3)
const timeline = ref<{ scrollToTime: (t: number) => void } | null>(null)
const playing = ref(false)
const avOffset = ref(0)

// 当前播放位置的块（用于视频字幕叠加 + 面板高亮）
const activeBlock = computed(() => {
  const t = currentTime.value
  return blocks.value.find((b) => t >= b.start && t <= b.end) ?? null
})

// 当前演出环节
const currentSegment = computed(() => {
  const t = currentTime.value
  return segments.value.find((s) => t >= s.t0 && t <= s.t1) ?? null
})

// 当前曲 DTW 映射加载
watch(
  () => currentSegment.value?.song_id,
  async (sid) => {
    if (!sid) {
      dtwMap.value = null
      return
    }
    try {
      dtwMap.value = await api.dtw(sid)
    } catch {
      dtwMap.value = null
    }
  },
)

function gotoSection(seg: Segment) {
  seek(seg.t0 + 0.5)
  timeline.value?.scrollToTime(seg.t0)
}

// 当前播放曲的 live 对齐歌词（宽容窗口: 歌曲前后 15s 仍算该曲, MC 间隙不断档）
const currentLiveSong = computed(() => {
  let best: { id: string; dist: number } | null = null
  for (const s of songs.value) {
    let dist = 0
    if (currentTime.value < s.t0) dist = s.t0 - currentTime.value
    else if (currentTime.value > s.t1) dist = currentTime.value - s.t1
    if (dist <= 15 && (best === null || dist < best.dist)) {
      best = { id: s.id, dist }
    }
  }
  if (!best) return null
  return lyricsLive.value.find((s) => s.id === best!.id) ?? null
})

const SEG_ICON: Record<string, string> = {
  intro: '⏸',
  mc: '🎤',
  song: '🎵',
  interval: '🎬',
  ed: '🔚',
}

function segName(seg: Segment): string {
  return seg.title ?? seg.label ?? seg.type
}

function songTitle(id: string): string {
  return songs.value.find((s) => s.id === id)?.title ?? ''
}

const openTags = ref<Tag[]>([])
const tagFilter = ref<'open' | 'done' | 'rejected'>('open')

// 全局撤销栈
interface UndoEntry {
  blockId?: string
  changes?: Record<string, unknown>
  shift?: { from: number; delta: number }
  restore?: Block
}
const undoStack = ref<UndoEntry[]>([])

async function undo() {
  const entry = undoStack.value.pop()
  if (!entry) return
  if (entry.shift) {
    await api.shift(entry.shift.from, -entry.shift.delta)
  } else if (entry.restore) {
    await api.createBlock(entry.restore)
  } else if (entry.blockId && entry.changes) {
    await api.putBlock(entry.blockId, entry.changes)
  }
  refreshAll()
}

// ---- 添加/删除块 ----
const addDialog = ref(false)
const addForm = ref({ start: 0, end: 5, ja: '', zh: '', kind: 'talk', song: '' })
const addBusy = ref(false)

function openAddDialog() {
  addForm.value = {
    start: Math.max(0, Math.round(currentTime.value - 1)),
    end: Math.round(currentTime.value + 4),
    ja: '',
    zh: '',
    kind: 'talk',
    song: '',
  }
  addDialog.value = true
}

async function submitAdd() {
  if (!addForm.value.ja.trim()) return
  addBusy.value = true
  try {
    await api.createBlock({
      start: addForm.value.start,
      end: addForm.value.end,
      ja: addForm.value.ja.trim(),
      zh: addForm.value.zh.trim(),
      kind: addForm.value.kind,
      song: addForm.value.song || '',
    })
    addDialog.value = false
    refreshAll()
  } finally {
    addBusy.value = false
  }
}

async function onDeleteBlock(b: Block) {
  if (!confirm(`删除块 ${b.id}？\n「${b.ja.slice(0, 30)}」`)) return
  undoStack.value.push({ restore: { ...b } })
  await api.deleteBlock(b.id)
  selected.value = null
  refreshAll()
}

const filteredTags = computed(() => tags.value.filter((t) => t.status === tagFilter.value))

// ---- 播放体验：变速 / A-B 循环 / 边界试听 ----
const playbackRate = ref(1)
const rates = [0.5, 1, 1.25, 1.5, 2]
const loopA = ref<number | null>(null)
const loopB = ref<number | null>(null)
const rateMenu = ref(false)

async function load() {
  meta.value = await api.meta()
  blocks.value = await api.blocks()
  tags.value = await api.tags()
  openTags.value = tags.value.filter((t) => t.status === 'open')
  songs.value = await api.songs()
  lyrics.value = await api.lyrics()
  try {
    const ll = await (await fetch('/api/lyrics_live')).json()
    lyricsLive.value = ll.songs ?? []
  } catch {
    lyricsLive.value = []
  }
  segments.value = await api.segments()
  const p = await fetch('/media/peaks')
  peaks.value = new Int16Array(await p.arrayBuffer())
  try {
    const s = await fetch('/media/spectrum')
    spectrum.value = new Uint8Array(await s.arrayBuffer())
    const m = await (await fetch('/media/spectrum/meta')).json()
    spectrumMeta.value = m
  } catch {
    /* spectrum 可选 */
  }
  // 初始定位到第一个字幕块（字幕从 5933s 才开始，避免打开停在空白开头）
  if (blocks.value.length) {
    const first = blocks.value[0]
    seek(first.start + 0.05)
    setTimeout(() => timeline.value?.scrollToTime(first.start), 150)
  }
}
onMounted(load)

function seek(t: number) {
  currentTime.value = t
  if (video.value) video.value.currentTime = t
}
function togglePlay() {
  const v = video.value
  if (!v) return
  if (v.paused) v.play()
  else v.pause()
}
function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
  switch (e.code) {
    case 'Space':
      e.preventDefault()
      togglePlay()
      break
    case 'ArrowLeft':
      e.preventDefault()
      goBlock(-1)
      break
    case 'ArrowRight':
      e.preventDefault()
      goBlock(1)
      break
    case 'BracketLeft':
      setLoopA()
      break
    case 'BracketRight':
      setLoopB()
      break
    case 'Backslash':
      clearLoop()
      break
    case 'KeyQ':
      previewEdge('before')
      break
    case 'KeyW':
      previewEdge('after')
      break
    case 'Digit1':
      setRate(0.5)
      break
    case 'Digit2':
      setRate(1)
      break
    case 'Digit3':
      setRate(1.25)
      break
    case 'Digit4':
      setRate(1.5)
      break
    case 'Digit5':
      setRate(2)
      break
  }
  if (e.ctrlKey && e.code === 'KeyZ') {
    e.preventDefault()
    undo()
  }
}
window.addEventListener('keydown', onKey)

async function refreshMeta() {
  meta.value = await api.meta()
}

async function refreshAll() {
  blocks.value = await api.blocks()
  meta.value = await api.meta()
}

async function onRetime(p: { block: Block; before: { start: number; end: number } }) {
  undoStack.value.push({ blockId: p.block.id, changes: { start: p.before.start, end: p.before.end } })
  await api.putBlock(p.block.id, { start: p.block.start, end: p.block.end })
  refreshMeta()
}

function onSelect(b: Block | null) {
  selected.value = b
}

function onBoxRange(r: { start: number; end: number }) {
  tagRange.value = r
  bulkBlocks.value = blocks.value.filter((b) => b.start <= r.end && b.end >= r.start).map((b) => b.id)
  tagDialog.value = true
}

function openTagForBlock(b: Block) {
  tagRange.value = { start: b.start, end: b.end, block_id: b.id }
  editingTag.value = null
  tagDialog.value = true
}

function openEditTag(t: Tag) {
  editingTag.value = t
  tagRange.value = null
  tagDialog.value = true
}

async function onShift(p: { from: number; delta: number }) {
  undoStack.value.push({ shift: { from: p.from, delta: p.delta } })
  await api.shift(p.from, p.delta)
  await refreshAll()
}

async function onTagCreated() {
  tags.value = await api.tags()
  openTags.value = tags.value.filter((t) => t.status === 'open')
  refreshMeta()
}

function exportSub(fmt: string, only?: 'green') {
  const q = only ? `&only=${only}` : ''
  window.open(`/api/export?fmt=${fmt}${q}`, '_blank')
}

function gotoTag(t: Tag) {
  if (t.block_id) {
    const b = blocks.value.find((x) => x.id === t.block_id)
    if (b) {
      selected.value = b
      seek(b.start + 0.05)
      return
    }
  }
  if (t.start !== undefined) seek(t.start)
}

async function removeTag(t: Tag) {
  await api.deleteTag(t.id)
  tags.value = await api.tags()
  openTags.value = tags.value.filter((x) => x.status === 'open')
  refreshMeta()
}

async function rejectTag(t: Tag) {
  await api.setTagStatus(t.id, 'rejected')
  tags.value = await api.tags()
  openTags.value = tags.value.filter((x) => x.status === 'open')
  refreshMeta()
}

async function reopenTag(t: Tag) {
  await api.setTagStatus(t.id, 'open')
  tags.value = await api.tags()
  openTags.value = tags.value.filter((x) => x.status === 'open')
  refreshMeta()
}

async function showGitLog() {
  gitLog.value = (await api.gitLog()).log
  gitDialog.value = true
}

function zoomBy(f: number) {
  pxPerSec.value = Math.min(400, Math.max(2, pxPerSec.value * f))
}

// ---- 播放体验：变速 / A-B 循环 / 边界试听 / 块导航 ----
function setRate(r: number) {
  playbackRate.value = r
  if (video.value) video.value.playbackRate = r
}

function setLoopA() {
  loopA.value = currentTime.value
  if (loopB.value !== null && loopA.value >= loopB.value) loopB.value = null
}
function setLoopB() {
  if (loopA.value === null || currentTime.value <= loopA.value) {
    setLoopA()
    loopB.value = loopA.value
    return
  }
  loopB.value = currentTime.value
  if (video.value) {
    video.value.currentTime = loopA.value
    video.value.play()
  }
}
function clearLoop() {
  loopA.value = null
  loopB.value = null
}

function onVideoTime() {
  if (video.value) currentTime.value = video.value.currentTime
  // A-B 循环回跳
  if (loopA.value !== null && loopB.value !== null && loopB.value > loopA.value) {
    if (currentTime.value >= loopB.value) {
      if (video.value) video.value.currentTime = loopA.value
      currentTime.value = loopA.value
    }
  }
}

function currentBlockIndex(): number {
  if (!selected.value) return -1
  return blocks.value.findIndex((b) => b.id === selected.value!.id)
}
function goBlock(delta: number) {
  const i = currentBlockIndex()
  if (i < 0) {
    if (blocks.value.length) selectBlock(blocks.value[0])
    return
  }
  const j = Math.min(blocks.value.length - 1, Math.max(0, i + delta))
  selectBlock(blocks.value[j])
}
function selectBlock(b: Block) {
  selected.value = b
  seek(b.start + 0.05)
}
function previewEdge(mode: 'before' | 'after') {
  const b = selected.value
  const v = video.value
  if (!b || !v) return
  const t = mode === 'before' ? Math.max(0, b.start - 0.5) : Math.max(0, b.end - 0.5)
  v.currentTime = t
  currentTime.value = t
  v.play()
}

const tagTypeLabel = (t: string) => TAG_TYPES[t] ?? t

function fmtTime(s: number): string {
  if (!isFinite(s)) return '0:00'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<template>
  <v-app class="agentisub-app" style="height: 100vh; overflow: hidden">
    <v-toolbar density="compact" color="#1e1e1e" class="agentisub-toolbar" style="height: 44px; flex: 0 0 auto">
      <v-toolbar-title style="font-size: 14px; flex-grow: 0">agentisub · Anima Ⅲ</v-toolbar-title>

      <!-- 缩放 -->
      <v-btn size="small" icon="mdi-magnify-minus-outline" variant="text" @click="zoomBy(0.7)" />
      <span class="d-inline-flex align-center px-1 text-caption" style="min-width: 48px">{{ pxPerSec }}px/s</span>
      <v-btn size="small" icon="mdi-magnify-plus-outline" variant="text" @click="zoomBy(1.4)" />

      <v-btn size="small" variant="text" :color="showSpectrum ? 'primary' : undefined" @click="showSpectrum = !showSpectrum">
        频谱
      </v-btn>
      <v-btn size="small" variant="text" :color="showDtw ? 'primary' : undefined" :disabled="!dtwMap" @click="showDtw = !showDtw">
        DTW
      </v-btn>
      <span class="text-caption text-grey">AV</span>
      <v-btn size="x-small" icon="mdi-minus" variant="text" density="compact" @click="avOffset = +(avOffset - 0.1).toFixed(1)" />
      <span class="text-caption" style="min-width: 34px">{{ avOffset.toFixed(1) }}s</span>
      <v-btn size="x-small" icon="mdi-plus" variant="text" density="compact" @click="avOffset = +(avOffset + 0.1).toFixed(1)" />
      <v-btn size="small" variant="text" @click="showGitLog">git</v-btn>
      <v-btn size="small" variant="text" color="orange-darken-3" @click="diffDialog = true">diff</v-btn>
      <v-btn size="small" variant="text" color="green" @click="openAddDialog">＋块</v-btn>
      <v-btn size="small" icon="mdi-undo" variant="text" :disabled="!undoStack.length" title="撤销 Ctrl+Z" @click="undo" />
      <v-btn size="small" variant="text" @click="drawer = !drawer">面板</v-btn>

      <v-menu>
        <template #activator="{ props }">
          <v-btn size="small" variant="text" v-bind="props">导出</v-btn>
        </template>
        <v-list density="compact">
          <v-list-item @click="exportSub('srt')">SRT（双语）</v-list-item>
          <v-list-item @click="exportSub('ass')">ASS（双语样式）</v-list-item>
          <v-divider />
          <v-list-item @click="exportSub('srt', 'green')">仅绿块 SRT</v-list-item>
          <v-list-item @click="exportSub('ass', 'green')">仅绿块 ASS</v-list-item>
        </v-list>
      </v-menu>
    </v-toolbar>

    <v-main class="d-flex pa-0" style="height: calc(100vh - 44px); overflow: hidden">
      <!-- 左主区：上视频(占剩余,含字幕叠加) + 下时间轴(固定紧凑) -->
      <div class="d-flex flex-column" style="flex: 1; min-width: 0">
        <!-- 播放器：16:9 自适应，随可用高度伸缩，字幕叠加 -->
        <div class="player-row d-flex align-start" style="padding: 6px 8px; background: #141414; border-bottom: 1px solid #2a2a2a">
          <div class="player-box" style="position: relative">
            <video
              ref="video"
              :src="'/media/video'"
              controls
              style="width: 100%; height: 100%; object-fit: cover; display: block"
              @timeupdate="onVideoTime"
              @play="playing = true"
              @pause="playing = false"
            />
            <div v-if="activeBlock" class="subtitle-overlay">
              <div class="sub-ja">{{ activeBlock.ja }}</div>
              <div v-if="activeBlock.zh" class="sub-zh">{{ activeBlock.zh }}</div>
            </div>
          </div>
          <div class="player-meta d-flex flex-column ml-3" style="height: 100%; min-width: 0">
            <div class="d-flex align-center text-caption" style="flex: 0 0 auto">
              <span class="text-grey">{{ fmtTime(currentTime) }} / {{ fmtTime(duration) }}</span>
              <v-menu v-model="rateMenu" :close-on-content-click="true">
                <template #activator="{ props }">
                  <v-btn size="x-small" variant="outlined" class="ml-2" v-bind="props">速度 {{ playbackRate }}x</v-btn>
                </template>
                <v-list density="compact">
                  <v-list-item v-for="r in rates" :key="r" :active="playbackRate === r" @click="setRate(r)">
                    <v-list-item-title>{{ r }}x</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-menu>
              <v-btn size="x-small" variant="outlined" class="ml-2" :color="loopA !== null ? 'primary' : undefined" @click="setLoopA">
                A
              </v-btn>
              <v-btn size="x-small" variant="outlined" class="ml-1" :color="loopB !== null ? 'primary' : undefined" @click="setLoopB">
                B
              </v-btn>
              <v-btn
                size="x-small"
                variant="text"
                class="ml-1"
                :disabled="loopA === null || loopB === null"
                @click="clearLoop"
              >
                清除循环
              </v-btn>
              <span v-if="loopA !== null && loopB !== null" class="ml-2 text-primary">
                ⟳ {{ fmtTime(loopA) }} – {{ fmtTime(loopB) }}
              </span>
              <v-spacer />
              <span class="text-grey mr-2">空格 播放 · ←→ 块 · Q/W 试听 · [ ] A/B · 1-5 变速</span>
            </div>

            <!-- 演出结构(窄条单列) + 歌词 并排（视频右侧） -->
            <div class="seg-nav d-flex mt-1" style="flex: 1; min-height: 0; align-items: stretch; overflow: hidden">
              <div class="d-flex flex-column" style="flex: 0 0 290px; min-width: 0; min-height: 0">
                <span class="text-caption text-grey" style="flex: 0 0 auto">演出</span>
                <div class="seg-scroll">
                  <div
                    v-for="(seg, i) in segments"
                    :key="i"
                    class="seg-item"
                    :class="{ 'seg-item-active': currentSegment === seg }"
                    :title="`${segName(seg)}${seg.outfit ? ' 👗' + seg.outfit : ''}${seg.guest ? ' 🤝' + seg.guest : ''}${seg.encore ? ' 🎉安可' : ''}${seg.no_official ? ' ⚠️无官方音源' : ''}${seg.green !== undefined ? ` ${seg.green}/${seg.yellow}/${seg.red}` : ''}`"
                    @click="gotoSection(seg)"
                  >
                    <span class="seg-line1">
                      <span class="seg-ic">{{ SEG_ICON[seg.type] ?? '•' }}</span>
                      <span class="seg-name">{{ segName(seg) }}</span>
                    </span>
                    <span class="seg-line2">{{ fmtTime(seg.t0) }} – {{ fmtTime(seg.t1) }}</span>
                  </div>
                </div>
              </div>
              <div class="d-flex flex-column ml-2" style="flex: 1; min-width: 0; min-height: 0; border-left: 1px solid #2a2a2a; overflow: hidden">
                <LiveLyrics :song="currentLiveSong" :current-time="currentTime" @seek="seek" />
              </div>
            </div>
          </div>
        </div>

        <!-- 时间轴：固定高度紧凑区 -->
        <div style="height: 360px; flex: 0 0 auto; position: relative">
          <TimelineCanvas
            v-if="peaks"
            ref="timeline"
            :blocks="blocks"
            :peaks="peaks"
            :spectrum="spectrum"
            :spectrum-meta="spectrumMeta"
            :current-time="currentTime"
            :px-per-sec="pxPerSec"
            :show-spectrum="showSpectrum"
            :duration="duration"
            :selected-id="selected?.id ?? null"
            :active-id="activeBlock?.id ?? null"
            :auto-follow="playing"
            :av-offset="avOffset"
            :dtw="showDtw ? dtwMap : null"
            @seek="seek"
            @select="onSelect"
            @retime="onRetime"
            @box-range="onBoxRange"
          />
        </div>
      </div>

      <!-- 右侧面板：块详情 + 标记队列 -->
      <v-navigation-drawer v-model="drawer" location="right" width="330" permanent class="border-s pt-0">
        <BlockPanel :block="selected" :tags="tags" :song-title="selected ? songTitle(selected.song) : ''" @refresh="refreshAll" @tag="openTagForBlock" @shift="onShift" @del="onDeleteBlock" />
        <v-divider class="my-2" />
        <div class="pa-3">
          <div class="d-flex align-center mb-1">
            <div class="text-subtitle-2">标记队列</div>
            <v-spacer />
            <v-chip size="x-small" color="green-darken-3" variant="flat" class="ml-1" title="绿色(已确认)">{{ meta.green }}</v-chip>
            <v-chip size="x-small" color="yellow-darken-3" variant="flat" class="ml-1" title="黄色(待校对)">{{ meta.yellow }}</v-chip>
            <v-chip size="x-small" color="red-darken-3" variant="flat" class="ml-1" title="红色(听写稿)">{{ meta.red }}</v-chip>
          </div>
          <v-btn-toggle v-model="tagFilter" density="compact" variant="outlined" mandatory class="mb-2 w-100">
            <v-btn size="x-small" value="open" class="flex-grow-1">待处理 {{ openTags.length }}</v-btn>
            <v-btn size="x-small" value="done" class="flex-grow-1">已完成 {{ tags.filter(t => t.status === 'done').length }}</v-btn>
            <v-btn size="x-small" value="rejected" class="flex-grow-1">已驳回 {{ tags.filter(t => t.status === 'rejected').length }}</v-btn>
          </v-btn-toggle>
          <div v-if="!filteredTags.length" class="text-caption text-grey">
            {{ tagFilter === 'open' ? '暂无待处理标记' : tagFilter === 'done' ? '暂无已完成标记' : '暂无驳回标记' }}
          </div>
          <div
            v-for="t in filteredTags"
            :key="t.id"
            class="d-flex align-start mb-1 pa-1"
            style="border-radius: 4px; cursor: pointer"
            @click="gotoTag(t)"
          >
            <v-chip size="x-small" :color="t.status === 'done' ? 'green-darken-3' : t.status === 'rejected' ? 'red-darken-3' : 'orange-darken-3'">{{ tagTypeLabel(t.type) }}</v-chip>
            <div class="ml-1 flex-grow-1" style="min-width: 0">
              <span
                class="text-caption d-block"
                style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap"
              >{{ t.note || (t.block_id ? t.block_id : `[${t.start?.toFixed(1)}s - ${t.end?.toFixed(1)}s]`) }}</span>
              <span v-if="t.reply" class="text-caption d-block" style="color: #81c784; font-size: 11px">💬 {{ t.reply }}</span>
            </div>
            <v-btn
              v-if="t.status === 'open'"
              size="x-small"
              icon="mdi-pencil-outline"
              variant="text"
              density="compact"
              title="编辑标记"
              @click.stop="openEditTag(t)"
            />
            <v-btn
              v-if="t.status === 'open'"
              size="x-small"
              icon="mdi-block"
              variant="text"
              density="compact"
              title="驳回（人工处理，agent 不再重试）"
              @click.stop="rejectTag(t)"
            />
            <v-btn
              v-if="t.status === 'rejected'"
              size="x-small"
              icon="mdi-restart"
              variant="text"
              density="compact"
              title="重新打开"
              @click.stop="reopenTag(t)"
            />
            <v-btn size="x-small" icon="mdi-close" variant="text" density="compact" @click.stop="removeTag(t)" />
          </div>
        </div>
      </v-navigation-drawer>
    </v-main>

    <TagDialog v-model="tagDialog" :range="tagRange" :bulk-blocks="bulkBlocks" :edit-tag="editingTag" @created="onTagCreated" />

    <!-- 添加块对话框 -->
    <v-dialog v-model="addDialog" width="460">
      <v-card>
        <v-card-title class="text-subtitle-1">添加字幕块</v-card-title>
        <v-card-text>
          <div class="d-flex align-center mb-2">
            <v-text-field v-model.number="addForm.start" type="number" label="开始(s)" density="compact" variant="outlined" hide-details class="mr-2" />
            <v-text-field v-model.number="addForm.end" type="number" label="结束(s)" density="compact" variant="outlined" hide-details />
          </div>
          <v-select
            v-model="addForm.kind"
            :items="[{ title: 'MC 说话', value: 'talk' }, { title: '歌词', value: 'lyric' }]"
            label="类型" density="compact" variant="outlined" hide-details class="mb-2"
          />
          <v-text-field v-if="addForm.kind === 'lyric'" v-model="addForm.song" label="曲目编号（如 05）" density="compact" variant="outlined" hide-details class="mb-2" />
          <v-textarea v-model="addForm.ja" label="日语" rows="2" density="compact" variant="outlined" hide-details class="mb-2" />
          <v-textarea v-model="addForm.zh" label="中文" rows="2" density="compact" variant="outlined" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="addDialog = false">取消</v-btn>
          <v-btn color="primary" :loading="addBusy" :disabled="!addForm.ja.trim()" @click="submitAdd">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="gitDialog" width="700">
      <v-card>
        <v-card-title>git log</v-card-title>
        <v-card-text>
          <pre class="selectable" style="white-space: pre-wrap; font-size: 12px">{{ gitLog }}</pre>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn text @click="gitDialog = false">关闭</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="diffDialog" width="680" scrollable>
      <v-card>
        <v-card-title>diff 视图</v-card-title>
        <v-card-text style="max-height: 70vh; overflow-y: auto">
          <DiffPanel :blocks="blocks" @refresh="refreshAll" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn text @click="diffDialog = false">关闭</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>

<style scoped>
.player-row {
  flex: 1;
  min-height: 0;
}
.player-box {
  height: 100%;
  aspect-ratio: 16 / 9;
  max-width: 100%;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  flex: 0 0 auto;
}
.player-meta {
  flex: 1;
  min-width: 0;
}
.subtitle-overlay {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 46px;
  pointer-events: none;
  text-align: center;
}
.sub-ja {
  font-size: 17px;
  color: #fff;
  font-weight: 600;
  text-shadow: 0 1px 3px #000, 0 0 8px #000;
}
.sub-zh {
  font-size: 13px;
  color: #ffd54f;
  text-shadow: 0 1px 3px #000, 0 0 6px #000;
  margin-top: 3px;
}
.song-row {
  display: flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.song-row:hover {
  background: #2a2a2a;
}
.song-row.song-active {
  background: #37474f;
}
.song-id {
  width: 32px;
  color: #888;
  flex: 0 0 auto;
}
.song-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-stats {
  flex: 0 0 auto;
  margin-left: 6px;
  font-size: 11px;
}
.seg-time {
  color: #78909c;
  font-size: 10.5px;
  line-height: 1.3;
  margin-left: 30px;
}
.seg-nav {
  flex: 1;
  min-height: 0;
  align-items: flex-start;
}
.seg-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}
.seg-scroll::-webkit-scrollbar {
  display: none;
}
.seg-item {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 2px 6px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  overflow: hidden;
}
.seg-item:hover {
  background: #2a2a2a;
}
.seg-item-active {
  background: #37474f;
}
.seg-line1 {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.seg-ic {
  flex: 0 0 auto;
  font-size: 11px;
}
.seg-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.seg-line2 {
  color: #78909c;
  font-size: 10px;
  line-height: 1.25;
  padding-left: 15px;
}
</style>
