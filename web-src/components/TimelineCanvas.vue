<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import type { Block } from '../types'
import { CONF_COLORS } from '../types'

const props = defineProps<{
  blocks: Block[]
  peaks: Int16Array
  spectrum: Uint8Array | null
  spectrumMeta: { fps: number; bands: number; frames: number } | null
  currentTime: number
  pxPerSec: number
  showSpectrum: boolean
  duration: number
  selectedId: string | null
  activeId: string | null
  autoFollow: boolean
  avOffset: number
  dtw: { song: string; live_t: number[]; studio_t: number[] } | null
}>()

const emit = defineEmits<{
  seek: [t: number]
  select: [b: Block | null]
  retime: [p: { block: Block; before: { start: number; end: number } }]
  boxRange: [r: { start: number; end: number }]
}>()

const wrap = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const scrollLeft = ref(0)
const wrapH = ref(292)
const rulerH = 22
// 每帧根据容器高度计算实际布局：标尺 + 紧凑波形 + 两个块带（字幕为主体）
function layout(H: number) {
  const avail = Math.max(80, H - rulerH)
  const waveH = Math.min(84, Math.max(48, Math.round(avail * 0.16)))
  const bandAvail = avail - waveH
  const bandH = Math.max(36, Math.round(bandAvail / 2))
  return { rulerH, bandH, waveH, lyricY: rulerH + waveH }
}

type Drag =
  | { mode: 'start' | 'end'; block: Block; moved: boolean; before: { start: number; end: number } }
  | { mode: 'box'; x0: number; t0: number; moved: boolean }
  | null

const drag = ref<Drag>(null)
const boxRect = ref<{ x0: number; x1: number } | null>(null)
const hover = ref<{ block: Block; x: number; y: number } | null>(null)
const specHover = ref<{ x: number; y: number; t: number; hz: number } | null>(null)

const peaksLen = () => props.peaks.length / 2 // 桶数（20 桶/s）

function tOf(px: number) {
  return (scrollLeft.value + px) / props.pxPerSec
}

function draw() {
  const c = canvas.value
  const w = wrap.value
  if (!c || !w) return
  const dpr = window.devicePixelRatio || 1
  const W = w.clientWidth
  const H = Math.max(120, wrapH.value)
  const L = layout(H)
  if (c.width !== W * dpr || c.height !== H * dpr) {
    c.width = W * dpr
    c.height = H * dpr
  }
  const ctx = c.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = '#181818'
  ctx.fillRect(0, 0, W, H)

  const t0 = scrollLeft.value / props.pxPerSec
  const t1 = (scrollLeft.value + W) / props.pxPerSec

  // ---- 波形 ----
  ctx.strokeStyle = '#4db6ac'
  ctx.lineWidth = 1
  const buckets = peaksLen()
  const bPerSec = buckets / props.duration
  ctx.beginPath()
  const step = Math.max(1, Math.floor(W / 2000))
  for (let x = 0; x < W; x += step) {
    const tt = t0 + x / props.pxPerSec + props.avOffset
    const b0 = Math.max(0, Math.floor(tt * bPerSec))
    const b1 = Math.min(buckets - 1, Math.ceil((tt + step / props.pxPerSec) * bPerSec))
    let mn = 0
    let mx = 0
    for (let i = b0; i <= b1; i++) {
      const v0 = props.peaks[i * 2]
      const v1 = props.peaks[i * 2 + 1]
      if (v0 < mn) mn = v0
      if (v1 > mx) mx = v1
    }
    const mid = L.rulerH + L.waveH / 2
    const amp = L.waveH / 2 - 4
    ctx.moveTo(x, mid - (mx / 32768) * amp)
    ctx.lineTo(x, mid - (mn / 32768) * amp)
  }
  ctx.stroke()

  // ---- 频谱（可选）----
  if (props.showSpectrum && props.spectrum && props.spectrumMeta) {
    const { fps, bands, frames } = props.spectrumMeta
    const img = ctx.createImageData(W, 60)
    for (let x = 0; x < W; x += 2) {
      const tt = t0 + x / props.pxPerSec + props.avOffset
      const f = Math.min(frames - 1, Math.max(0, Math.floor(tt * fps)))
      for (let y = 0; y < 60; y++) {
        const band = Math.floor(((59 - y) / 60) * bands)
        const v = props.spectrum[f * bands + band]
        const idx = (y * W + x) * 4
        img.data[idx] = v
        img.data[idx + 1] = v
        img.data[idx + 2] = Math.min(255, v + 40)
        img.data[idx + 3] = 200
      }
    }
    ctx.putImageData(img, 0, L.lyricY)
    ctx.fillStyle = 'rgba(24,24,24,0.35)'
    ctx.fillRect(0, L.lyricY, W, 60)
  }

  // ---- 字幕块 ----
  for (const b of props.blocks) {
    if (b.end < t0 || b.start > t1) continue
    const x0 = b.start * props.pxPerSec - scrollLeft.value
    const x1 = b.end * props.pxPerSec - scrollLeft.value
    const band = b.kind === 'lyric' ? 0 : 1
    const y = L.lyricY + band * L.bandH + 3
    const h = L.bandH - 6
    ctx.fillStyle = CONF_COLORS[b.confidence] ?? '#9e9e9e'
    if (b.confidence === 'green') ctx.globalAlpha = 0.75
    else ctx.globalAlpha = 0.95
    ctx.fillRect(x0, y, Math.max(2, x1 - x0), h)
    ctx.globalAlpha = 1
    if (b.id === props.selectedId) {
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.strokeRect(x0, y, Math.max(2, x1 - x0), h)
    }
    if (b.id === props.activeId) {
      ctx.strokeStyle = '#ffd54f'
      ctx.lineWidth = 2.5
      ctx.strokeRect(x0 - 1, y - 1, Math.max(2, x1 - x0) + 2, h + 2)
    }
    if (x1 - x0 > 26) {
      ctx.save()
      ctx.beginPath()
      ctx.rect(x0 + 3, y + 4, x1 - x0 - 6, h - 8)
      ctx.clip()
      // 日语主行
      ctx.fillStyle = '#111'
      ctx.font = '14px "Yu Gothic UI", sans-serif'
      ctx.fillText(b.ja.slice(0, 60), x0 + 6, y + 20)
      // 中文副行（块足够高时）
      if (h > 52 && b.zh) {
        ctx.fillStyle = '#555'
        ctx.font = '11px "Yu Gothic UI", sans-serif'
        ctx.fillText(b.zh.replace(/\n/g, ' ').slice(0, 60), x0 + 6, y + 38)
      }
      ctx.restore()
    }
  }

  // ---- 框选 ----
  if (boxRect.value) {
    ctx.fillStyle = 'rgba(100,180,255,0.2)'
    ctx.strokeStyle = '#64b4ff'
    const x0 = Math.min(boxRect.value.x0, boxRect.value.x1)
    const x1 = Math.max(boxRect.value.x0, boxRect.value.x1)
    ctx.fillRect(x0, rulerH, x1 - x0, H - rulerH)
    ctx.strokeRect(x0, rulerH, x1 - x0, H - rulerH)
  }

  // ---- 标尺 ----
  ctx.fillStyle = '#666'
  ctx.font = '11px sans-serif'
  const tickEvery = props.pxPerSec >= 100 ? 10 : props.pxPerSec >= 25 ? 60 : 300
  const firstTick = Math.ceil(t0 / tickEvery) * tickEvery
  for (let t = firstTick; t < t1; t += tickEvery) {
    const x = t * props.pxPerSec - scrollLeft.value
    ctx.fillRect(x, rulerH - 6, 1, 6)
    const mm = Math.floor(t / 60)
    ctx.fillText(`${Math.floor(mm / 60)}:${String(mm % 60).padStart(2, '0')}`, x + 3, rulerH - 8)
  }

  // ---- DTW 映射曲线（live→studio, 台阶=live 删段/插段）----
  if (props.dtw && props.dtw.live_t.length > 1) {
    const lt = props.dtw.live_t
    const st = props.dtw.studio_t
    let minS = Infinity
    let maxS = -Infinity
    for (const v of st) {
      if (v < minS) minS = v
      if (v > maxS) maxS = v
    }
    const spanS = Math.max(1, maxS - minS)
    const y0 = rulerH + 3
    const h = 24
    ctx.strokeStyle = '#ba68c8'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    let prevInView = false
    for (let i = 0; i < lt.length; i++) {
      const x = lt[i] * props.pxPerSec - scrollLeft.value
      const inView = x >= -20 && x <= W + 20
      if (!inView) {
        prevInView = false
        continue
      }
      const y = y0 + (1 - (st[i] - minS) / spanS) * h
      if (!prevInView) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
      prevInView = true
    }
    ctx.stroke()
    // 当前播放位置在曲线上的点
    const cx = props.currentTime * props.pxPerSec - scrollLeft.value
    if (cx >= -5 && cx <= W + 5) {
      // 线性查找当前 live 时间对应的 studio 时间
      let stNow = null
      for (let i = 0; i < lt.length - 1; i++) {
        if (props.currentTime >= lt[i] && props.currentTime <= lt[i + 1]) {
          const f = (props.currentTime - lt[i]) / Math.max(1e-6, lt[i + 1] - lt[i])
          stNow = st[i] + f * (st[i + 1] - st[i])
          break
        }
      }
      if (stNow !== null) {
        const cy = y0 + (1 - (stNow - minS) / spanS) * h
        ctx.fillStyle = '#ffd54f'
        ctx.beginPath()
        ctx.arc(cx, cy, 3.5, 0, Math.PI * 2)
        ctx.fill()
      }
    }
  }

  // ---- 播放头 ----
  const px = props.currentTime * props.pxPerSec - scrollLeft.value
  ctx.strokeStyle = '#ff5252'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(px, 0)
  ctx.lineTo(px, H)
  ctx.stroke()

  // ---- 悬停 tooltip ----
  if (specHover.value && !drag.value) {
    const sh = specHover.value
    const mm = Math.floor(sh.t / 60)
    const text = `${Math.floor(mm / 60)}:${String(mm % 60).padStart(2, '0')} · ${sh.hz}Hz`
    ctx.font = '12px "Yu Gothic UI", sans-serif'
    const tw = ctx.measureText(text).width
    const tx = Math.min(Math.max(4, sh.x + 12), W - tw - 8)
    ctx.fillStyle = 'rgba(0,0,0,0.88)'
    ctx.strokeStyle = '#555'
    ctx.beginPath()
    ctx.roundRect(tx - 6, sh.y - 4, tw + 12, 22, 4)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = '#4db6ac'
    ctx.fillText(text, tx, sh.y + 11)
  } else if (hover.value && !drag.value) {
    const hb = hover.value
    const text = `${hb.block.id} · ${hb.block.start.toFixed(2)}–${hb.block.end.toFixed(2)} · ${hb.block.ja.slice(0, 30)}`
    ctx.font = '12px "Yu Gothic UI", sans-serif'
    const tw = ctx.measureText(text).width
    const tx = Math.min(Math.max(4, hb.x + 12), W - tw - 8)
    const ty = Math.max(4, hb.y - 28)
    ctx.fillStyle = 'rgba(0,0,0,0.88)'
    ctx.strokeStyle = '#555'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.roundRect(tx - 6, ty - 4, tw + 12, 22, 4)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = '#eee'
    ctx.fillText(text, tx, ty + 11)
  }
}

let raf = 0
function scheduleDraw() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    draw()
  })
}

function hitTest(x: number, y: number): { block: Block; mode: 'start' | 'end' | 'body' } | null {
  const t = tOf(x)
  const L = layout(Math.max(120, wrapH.value))
  for (const b of props.blocks) {
    if (t < b.start || t > b.end) continue
    const band = b.kind === 'lyric' ? 0 : 1
    const by = L.lyricY + band * L.bandH
    if (y < by || y > by + L.bandH) continue
    const bx0 = b.start * props.pxPerSec - scrollLeft.value
    const bx1 = b.end * props.pxPerSec - scrollLeft.value
    if (Math.abs(x - bx0) <= 5) return { block: b, mode: 'start' }
    if (Math.abs(x - bx1) <= 5) return { block: b, mode: 'end' }
    return { block: b, mode: 'body' }
  }
  return null
}

function onDown(e: MouseEvent) {
  const rect = canvas.value!.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const hit = hitTest(x, y)
  if (hit) {
    if (hit.mode === 'body') {
      emit('select', hit.block)
      emit('seek', hit.block.start + 0.05)
    } else {
      drag.value = { mode: hit.mode, block: hit.block, moved: false, before: { start: hit.block.start, end: hit.block.end } }
      emit('select', hit.block)
    }
  } else {
    emit('select', null)
    drag.value = { mode: 'box', x0: x, t0: tOf(x), moved: false }
  }
}

function onMove(e: MouseEvent) {
  const rect = canvas.value!.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const d = drag.value
  if (!d) {
    // 频谱区悬停：时间+频率
    if (props.showSpectrum && props.spectrumMeta) {
      const L0 = layout(Math.max(120, wrapH.value))
      const specY0 = L0.lyricY
      const specH = 60
      if (y >= specY0 && y <= specY0 + specH) {
        const t = tOf(x)
        const band = Math.max(0, Math.min(props.spectrumMeta.bands - 1, Math.floor(((specY0 + specH - y) / specH) * props.spectrumMeta.bands)))
        const hz = Math.round((band / props.spectrumMeta.bands) * 8000)
        specHover.value = { x, y: specY0 + 8, t, hz }
        scheduleDraw()
        return
      }
    }
    specHover.value = null
    // 悬停检测
    const hit = hitTest(x, y)
    if (hit) {
      hover.value = { block: hit.block, x, y }
      scheduleDraw()
    } else if (hover.value) {
      hover.value = null
      scheduleDraw()
    }
    return
  }
  d.moved = true
  if (d.mode === 'box') {
    boxRect.value = { x0: d.x0, x1: x }
    scheduleDraw()
    return
  }
  const t = tOf(x)
  const b = d.block
  if (d.mode === 'start') {
    b.start = Math.min(t, b.end - 0.1)
  } else {
    b.end = Math.max(t, b.start + 0.1)
  }
  scheduleDraw()
}

function onUp() {
  hover.value = null
  const d = drag.value
  if (!d) return
  if (d.mode === 'box') {
    if (d.moved && boxRect.value) {
      const tA = tOf(Math.min(boxRect.value.x0, boxRect.value.x1))
      const tB = tOf(Math.max(boxRect.value.x0, boxRect.value.x1))
      emit('boxRange', { start: Math.max(0, tA), end: tB })
    } else if (!d.moved) {
      // 单击空白：seek 到该时间
      emit('seek', tOf(d.x0))
    }
  }
  if ((d.mode === 'start' || d.mode === 'end') && d.moved) {
    emit('retime', { block: d.block, before: d.before })
  }
  drag.value = null
  boxRect.value = null
  scheduleDraw()
}

function onScroll() {
  scrollLeft.value = wrap.value?.scrollLeft ?? 0
  scheduleDraw()
}

// 供外部调用：滚动到某时间（放在视口左侧 30% 处，保留前文）
function scrollToTime(t: number) {
  const w = wrap.value
  if (!w) return
  const target = Math.max(0, t * props.pxPerSec - w.clientWidth * 0.3)
  w.scrollLeft = target
  scrollLeft.value = w.scrollLeft
  scheduleDraw()
}

defineExpose({ scrollToTime })

function onWheel(e: WheelEvent) {
  if (e.shiftKey) {
    e.preventDefault()
    const f = e.deltaY < 0 ? 1.3 : 0.77
    const px = e.offsetX
    const t = tOf(px)
    const npps = Math.min(400, Math.max(2, props.pxPerSec * f))
    const parent = wrap.value
    if (parent) {
      // 调整 scrollLeft 使鼠标下时间点保持在原位
      const newScroll = t * npps - px
      scrollLeft.value = Math.max(0, newScroll)
      requestAnimationFrame(() => {
        if (parent) parent.scrollLeft = scrollLeft.value
      })
    }
  }
}

watch(
  () => [props.blocks, props.currentTime, props.pxPerSec, props.showSpectrum, props.selectedId, props.dtw],
  () => scheduleDraw(),
  { deep: false },
)

// 播放时自动跟随：播放头超出视口 85% 或回退到左侧时滚动
watch(
  () => props.currentTime,
  (t) => {
    if (!props.autoFollow) return
    const w = wrap.value
    if (!w) return
    const W = w.clientWidth
    const px = t * props.pxPerSec - scrollLeft.value
    if (px > W * 0.85 || px < 0) {
      w.scrollLeft = Math.max(0, t * props.pxPerSec - W * 0.2)
      scrollLeft.value = w.scrollLeft
    }
  },
)

let ro: ResizeObserver | null = null

onMounted(() => {
  wrap.value?.addEventListener('scroll', onScroll)
  if (wrap.value) {
    ro = new ResizeObserver(() => {
      wrapH.value = wrap.value?.clientHeight ?? 292
      scheduleDraw()
    })
    ro.observe(wrap.value)
    wrapH.value = wrap.value.clientHeight || 292
  }
  scheduleDraw()
})

onBeforeUnmount(() => {
  wrap.value?.removeEventListener('scroll', onScroll)
  ro?.disconnect()
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <div
    ref="wrap"
    style="overflow-x: auto; overflow-y: hidden; height: 100%; position: relative; background: #181818"
  >
    <div :style="{ width: (duration * pxPerSec) + 'px', height: '1px' }" />
    <canvas
      ref="canvas"
      :style="{ position: 'sticky', left: 0, top: 0, display: 'block', width: '100%', height: wrapH + 'px' }"
      @mousedown="onDown"
      @mousemove="onMove"
      @mouseup="onUp"
      @mouseleave="onUp"
      @wheel="onWheel"
    />
  </div>
</template>
