<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'
import type { Block, Tag } from '../types'
import { TAG_TYPES, CONF_COLORS } from '../types'

const props = defineProps<{ block: Block | null; tags: Tag[]; songTitle: string }>()
const emit = defineEmits<{ refresh: []; tag: [b: Block]; shift: [p: { from: number; delta: number }]; del: [b: Block] }>()

const ja = ref('')
const zh = ref('')
const saving = ref(false)
const shiftDelta = ref('')
const shiftBusy = ref(false)
const revertingIdx = ref(-1)

watch(
  () => props.block,
  (b) => {
    ja.value = b?.ja ?? ''
    zh.value = b?.zh ?? ''
  },
  { immediate: true },
)

async function save() {
  if (!props.block) return
  saving.value = true
  try {
    await api.putBlock(props.block.id, { ja: ja.value, zh: zh.value })
    emit('refresh')
  } finally {
    saving.value = false
  }
}

async function applyShift() {
  if (!props.block) return
  const d = parseFloat(shiftDelta.value)
  if (!isFinite(d) || d === 0) return
  shiftBusy.value = true
  try {
    emit('shift', { from: props.block.start, delta: d })
    shiftDelta.value = ''
  } finally {
    shiftBusy.value = false
  }
}

async function revert(idx: number) {
  if (!props.block) return
  revertingIdx.value = idx
  try {
    await api.revertBlock(props.block.id, idx)
    emit('refresh')
  } finally {
    revertingIdx.value = -1
  }
}

const fmt = (s: number) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = (s % 60).toFixed(1)
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(4, '0')}`
}

const blockTags = () => (props.block ? props.tags.filter((t) => props.block!.tags.includes(t.id)) : [])
const tagTypeLabel = (t: string) => TAG_TYPES[t] ?? t
</script>

<style scoped>
</style>

<template>
  <div class="pa-3">
    <template v-if="block">
      <div class="text-caption text-grey mb-1">
        {{ block.id }} · {{ block.kind === 'lyric' ? `歌曲 ${block.song}${songTitle ? '「' + songTitle + '」' : ''}` : 'MC' }}
      </div>
      <div class="text-caption mb-2">
        <span :style="{ color: CONF_COLORS[block.confidence] }">●</span>
        {{ fmt(block.start) }} → {{ fmt(block.end) }}
        <span class="text-grey">（{{ block.evidence.method }}）</span>
      </div>
      <div class="text-caption text-grey mb-1">{{ block.evidence.detail }}</div>

      <v-textarea v-model="ja" label="日语" rows="3" variant="outlined" density="compact" hide-details class="mb-2" />
      <v-textarea v-model="zh" label="中文" rows="3" variant="outlined" density="compact" hide-details class="mb-2" />
      <div class="d-flex align-center">
        <v-btn size="small" color="primary" :loading="saving" @click="save">保存文本</v-btn>
        <v-btn size="small" color="orange-darken-3" variant="tonal" class="ml-2" @click="emit('tag', block)">🕐 打标记</v-btn>
        <v-spacer />
        <v-btn size="small" icon="mdi-delete-outline" variant="text" color="error" title="删除块" @click="emit('del', block)" />
      </div>

      <div class="mt-3">
        <div class="text-caption text-grey mb-1">整段平移（从本块起，之后所有块）</div>
        <div class="d-flex align-center">
          <v-text-field
            v-model="shiftDelta"
            type="number"
            step="0.1"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="±秒，如 0.5 或 -0.3"
            class="mr-2"
          />
          <v-btn size="small" color="primary" variant="tonal" :loading="shiftBusy" @click="applyShift">平移</v-btn>
        </div>
      </div>

      <div v-if="blockTags().length" class="mt-3">
        <div class="text-subtitle-2 mb-1">本块标记</div>
        <div v-for="t in blockTags()" :key="t.id" class="mb-1">
          <v-chip size="x-small" color="orange-darken-3">{{ tagTypeLabel(t.type) }}</v-chip>
          <span class="text-caption">{{ t.note }}</span>
          <v-chip size="x-small" :color="t.status === 'done' ? 'green' : t.status === 'rejected' ? 'red' : 'grey'" class="ml-1">{{ t.status }}</v-chip>
          <div v-if="t.reply" class="text-caption text-grey mt-1">💬 {{ t.reply }}</div>
        </div>
      </div>

      <div v-if="block.history.length" class="mt-3">
        <div class="text-subtitle-2 mb-1">修改历史（最近 {{ Math.min(5, block.history.length) }}）</div>
        <div
          v-for="(h, i) in [...block.history].map((x, j) => ({ ...x, idx: j })).reverse().slice(0, 5)"
          :key="i"
          class="d-flex align-center text-caption text-grey mb-1"
        >
          <span class="flex-grow-1" style="min-width: 0">
            [{{ h.ts?.slice(11, 19) }}] {{ h.actor === 'agent' ? '🤖 agent' : h.actor === 'revert' ? '↩ 回滚' : '🧑 你' }}
            <span v-if="h.reply">— {{ h.reply }}</span>
          </span>
          <v-btn
            size="x-small"
            icon="mdi-undo-variant"
            variant="text"
            density="compact"
            :loading="revertingIdx === h.idx"
            :disabled="h.actor === 'revert'"
            @click="revert(h.idx)"
          />
        </div>
      </div>

    </template>
    <template v-else>
      <div class="text-body-2 text-grey">点击时间轴上的字幕块查看详情<br />Shift+滚轮缩放 · 拖动块边缘改轴 · 空白处拖拽框选打标</div>
    </template>
  </div>
</template>
