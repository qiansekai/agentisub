<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '../api'
import type { Block, HistoryEntry } from '../types'

const props = defineProps<{ blocks: Block[] }>()
const emit = defineEmits<{ refresh: [] }>()

const reverting = ref<string | null>(null)
const error = ref<string | null>(null)
const filter = ref<'all' | 'agent' | 'ui'>('all')

const FIELD_LABELS: Record<string, string> = {
  ja: '日语',
  zh: '中文',
  start: '开始',
  end: '结束',
  confidence: '置信度',
}
const CONF_LABELS: Record<string, string> = {
  green: '绿',
  yellow: '黄',
  red: '红',
  gray: '灰',
}

// 有 history 的块；每条 entry 携带其在 block.history 中的原始索引（idx 用于回滚）
const changed = computed(() =>
  props.blocks
    .filter((b) => b.history.length > 0)
    .map((b) => ({
      block: b,
      entries: b.history
        .map((h, idx) => ({ h, idx }))
        .filter(({ h }) => filter.value === 'all' || h.actor === filter.value)
        .reverse(),
    }))
    .filter((x) => x.entries.length > 0)
    .sort((a, b) => b.entries[0].h.ts.localeCompare(a.entries[0].h.ts)),
)

const totalChanges = computed(() => props.blocks.reduce((n, b) => n + b.history.length, 0))

function changedFields(h: HistoryEntry): string[] {
  const keys = ['ja', 'zh', 'start', 'end', 'confidence'] as const
  const b = h.before ?? {}
  const a = h.after ?? {}
  return keys.filter((k) => {
    const bv = b[k]
    const av = a[k]
    if (bv === undefined && av === undefined) return false
    if (typeof bv === 'number' && typeof av === 'number') return Math.abs(bv - av) > 0.001
    return bv !== av
  })
}

const fmt = (v: unknown, k?: string): string => {
  if (v === undefined || v === null) return '—'
  if (typeof v === 'number') return v.toFixed(2) + 's'
  if (k === 'confidence') return CONF_LABELS[String(v)] ?? String(v)
  return String(v)
}

const actorLabel = (a: string) =>
  a === 'agent' ? '🤖 agent' : a === 'revert' ? '↩ 回滚' : a === 'ui' ? '🧑 你' : a

async function revert(blockId: string, idx: number) {
  reverting.value = blockId + '#' + idx
  error.value = null
  try {
    await api.revertBlock(blockId, idx)
    emit('refresh')
  } catch (e) {
    error.value = `回滚失败: ${(e as Error).message}`
  } finally {
    reverting.value = null
  }
}
</script>

<template>
  <div class="pa-3">
    <div class="d-flex align-center mb-2">
      <div class="text-subtitle-2">diff 视图</div>
      <v-spacer />
      <v-btn-toggle v-model="filter" density="compact" variant="outlined" mandatory class="mr-2">
        <v-btn size="x-small" value="all">全部</v-btn>
        <v-btn size="x-small" value="agent">🤖 agent</v-btn>
        <v-btn size="x-small" value="ui">🧑 你</v-btn>
      </v-btn-toggle>
      <v-chip size="small" color="primary" variant="tonal">{{ totalChanges }} 条改动</v-chip>
    </div>

    <div v-if="error" class="text-caption text-error mb-2">{{ error }}</div>

    <div v-if="!changed.length" class="text-body-2 text-grey">
      暂无改动。点击块改文本、或等 agent 修复后，历史记录会出现在这里，可逐条回滚。
    </div>

    <div v-for="{ block, entries } in changed" :key="block.id" class="mb-3">
      <div class="text-caption text-grey mb-1">
        {{ block.id }}
        <span v-if="block.kind === 'lyric'">· 歌曲 {{ block.song }}</span>
        <span v-else>· MC</span>
      </div>

      <div
        v-for="{ h, idx } in entries"
        :key="idx"
        class="d-flex justify-space-between align-start mb-2 pa-2"
        style="border: 1px solid #333; border-radius: 6px; background: #1e1e1e"
      >
        <div class="flex-grow-1" style="min-width: 0">
          <div class="text-caption text-grey mb-1">
            {{ actorLabel(h.actor) }} · {{ h.ts?.slice(11, 19) }}
            <span v-if="h.reply" style="color: #81c784">— {{ h.reply }}</span>
          </div>

          <div v-if="changedFields(h).length === 0" class="text-caption text-grey">（无字段变更记录）</div>

          <div
            v-for="k in ['ja', 'zh', 'start', 'end', 'confidence']"
            v-show="changedFields(h).includes(k)"
            :key="k"
            class="text-caption mb-1"
            style="line-height: 1.4"
          >
            <span class="text-grey">{{ FIELD_LABELS[k] ?? k }}: </span>
            <del style="color: #e57373">{{ fmt(h.before?.[k], k) }}</del>
            <span class="text-grey mx-1">→</span>
            <ins style="color: #81c784">{{ fmt(h.after?.[k], k) }}</ins>
          </div>
        </div>

        <v-btn
          size="x-small"
          color="orange-darken-3"
          variant="tonal"
          :loading="reverting === block.id + '#' + idx"
          :disabled="h.actor === 'revert'"
          class="ml-2"
          @click="revert(block.id, idx)"
        >
          回滚
        </v-btn>
      </div>
    </div>
  </div>
</template>
