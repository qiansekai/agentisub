<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

export interface LiveLyricLine {
  ja: string
  zh: string
  roma: string
  t: number
}
export interface LiveLyricSong {
  id: string
  title: string
  lines: LiveLyricLine[]
}

const props = defineProps<{ song: LiveLyricSong | null; currentTime: number }>()
const emit = defineEmits<{ seek: [t: number] }>()

const container = ref<HTMLDivElement | null>(null)

// 当前行: 最后一个 t <= currentTime
const currentIdx = computed(() => {
  if (!props.song || !props.song.lines.length) return -1
  let idx = -1
  for (let i = 0; i < props.song.lines.length; i++) {
    if (props.song.lines[i].t <= props.currentTime) idx = i
    else break
  }
  return idx
})

// 当前行自动聚焦(滚动到容器中央)
watch(currentIdx, async (idx) => {
  if (idx < 0 || !container.value) return
  await nextTick()
  const rows = container.value.querySelectorAll('.ll-row')
  const row = rows[idx] as HTMLElement | undefined
  if (!row) return
  const ch = container.value.clientHeight
  const target = row.offsetTop - ch / 2 + row.clientHeight / 2
  container.value.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
})

function seekTo(t: number) {
  emit('seek', t + 0.1)
}
</script>

<template>
  <div class="live-lyrics" style="border-bottom: 1px solid #333">
    <div class="d-flex align-center px-2 pt-1">
      <span class="text-caption text-grey">歌词</span>
      <span v-if="song" class="text-caption ml-2" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ song.title }}</span>
      <v-spacer />
      <span v-if="song" class="text-caption text-grey">{{ currentIdx + 1 }}/{{ song.lines.length }}</span>
    </div>
    <div ref="container" class="ll-container px-2 pb-1">
      <div v-if="!song" class="text-caption text-grey pa-2">
        当前段无歌词（MC / 无网易云收录）
      </div>
      <div
        v-for="(ln, i) in (song?.lines ?? [])"
        :key="i"
        class="ll-row"
        :class="{ 'll-now': i === currentIdx }"
        @click="seekTo(ln.t)"
      >
        <div class="ll-ja">{{ ln.ja }}</div>
        <div v-if="ln.roma" class="ll-roma">{{ ln.roma }}</div>
        <div v-if="ln.zh" class="ll-zh">{{ ln.zh }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.live-lyrics {
  background: transparent;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ll-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scroll-behavior: smooth;
  scrollbar-width: none;
}
.ll-container::-webkit-scrollbar {
  display: none;
}
.ll-row {
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  line-height: 1.35;
}
.ll-row:hover {
  background: #232323;
}
.ll-now {
  background: #37474f;
}
.ll-now .ll-ja {
  color: #ffd54f;
  font-weight: 600;
}
.ll-ja {
  font-size: 12px;
}
.ll-roma {
  color: #78909c;
  font-size: 10px;
  line-height: 1.3;
}
.ll-zh {
  color: #ffd54f;
  font-size: 11px;
  opacity: 0.85;
  line-height: 1.3;
}
</style>
