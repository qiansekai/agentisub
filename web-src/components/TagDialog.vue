<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'
import { TAG_TYPES } from '../types'

const props = defineProps<{
  modelValue: boolean
  range: { start: number; end: number; block_id?: string } | null
  bulkBlocks: string[]
  editTag: import('../types').Tag | null
}>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; created: [] }>()

const types = ref<string[]>(['retime'])
const note = ref('')
const saving = ref(false)
const applyAll = ref(false)

const fmt = (s: number) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}:${String(m).padStart(2, '0')}:${String((s % 60).toFixed(1)).padStart(4, '0')}`
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      note.value = props.editTag?.note ?? ''
      types.value = props.editTag ? [props.editTag.type] : ['retime']
      applyAll.value = false
    }
  },
)

async function submit() {
  if (!props.range && !props.editTag) return
  if (!types.value.length) return
  saving.value = true
  try {
    if (props.editTag) {
      // 编辑模式: 更新标记
      await api.putTag(props.editTag.id, { type: types.value[0], note: note.value })
    } else {
      // 目标块集合: 批量 或 单块/范围
      const targets: { block_id?: string; start?: number; end?: number }[] = []
      if (applyAll.value && props.bulkBlocks.length > 1) {
        for (const id of props.bulkBlocks) targets.push({ block_id: id })
      } else if (props.range) {
        targets.push({
          block_id: props.range.block_id,
          start: props.range.block_id ? undefined : Math.round(props.range.start * 10) / 10,
          end: props.range.block_id ? undefined : Math.round(props.range.end * 10) / 10,
        })
      }
      // 类型 × 目标 双重循环
      for (const t of targets) {
        for (const ty of types.value) {
          await api.postTag({ type: ty, note: note.value, block_id: t.block_id, start: t.start, end: t.end })
        }
      }
    }
    emit('created')
    emit('update:modelValue', false)
  } finally {
    saving.value = false
  }
}

const close = () => emit('update:modelValue', false)
</script>

<template>
  <v-dialog :model-value="modelValue" width="440" @update:model-value="close">
    <v-card>
      <v-card-title class="text-subtitle-1">
        {{ editTag ? `编辑标记 ${editTag.id}` : '添加标记' }}
        <span v-if="range" class="text-caption text-grey ml-2">
          {{ range.block_id ? `块 ${range.block_id}` : `范围 ${fmt(range.start)} - ${fmt(range.end)}` }}
        </span>
      </v-card-title>
      <v-card-text>
        <v-select
          v-model="types"
          :items="Object.entries(TAG_TYPES).map(([k, v]) => ({ title: v, value: k }))"
          :label="editTag ? '类型' : '类型（可多选）'"
          density="compact"
          variant="outlined"
          :multiple="!editTag"
          chips
          hide-details
          class="mb-3"
        />
        <v-checkbox
          v-if="!editTag && bulkBlocks.length > 1"
          v-model="applyAll"
          density="compact"
          hide-details
          :label="`应用到范围内所有 ${bulkBlocks.length} 个块`"
          class="mb-2"
        />
        <v-text-field v-model="note" label="备注（可选，告诉 agent 你的想法）" density="compact" variant="outlined" hide-details @keydown.enter="submit" />
        <div v-if="!editTag && applyAll && bulkBlocks.length > 1 && types.length > 1" class="text-caption text-grey mt-2">
          将创建 {{ bulkBlocks.length }} 块 × {{ types.length }} 类型 = {{ bulkBlocks.length * types.length }} 个标记
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn text @click="close">取消</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!types.length" @click="submit">提交标记</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
