<template>
  <div class="hit-list">
    <p v-if="!hits.length" class="hit-empty">该字段无实际命中区间</p>
    <article v-for="(hit, idx) in hits" :key="idx" class="hit-card" :class="`hit-${hit.field}`">
      <header class="hit-meta">
        <span class="hit-field">{{ fieldLabel(hit.field) }}</span>
        <span v-if="hit.seg_heading" class="hit-seg">小节：{{ hit.seg_heading }}</span>
        <span class="hit-range">[{{ hit.start }}, {{ hit.end }}) · {{ hit.end - hit.start }}字</span>
      </header>
      <!-- 只展示当时实际命中的文字区间，不展示历史样本全文 -->
      <blockquote class="hit-text">“{{ hit.text }}”</blockquote>
    </article>
  </div>
</template>

<script setup lang="ts">
import type { HitInterval } from '@/api/webSample'

defineProps<{ hits: HitInterval[] }>()

function fieldLabel(field: string): string {
  return field === 'title' ? '标题命中' : '正文命中'
}
</script>

<style scoped>
.hit-list { display: flex; flex-direction: column; gap: 8px; }
.hit-empty { color: var(--muted); font-size: 12px; margin: 4px 0; }
.hit-card { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: #fbfdff; }
.hit-title { border-left: 3px solid #7c3aed; }
.hit-body { border-left: 3px solid #0f766e; }
.hit-meta { display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
.hit-field { font-weight: 600; color: #1f2937; }
.hit-seg { background: #ecfdf5; color: #0f766e; border-radius: 4px; padding: 1px 6px; }
.hit-range { font-variant-numeric: tabular-nums; }
.hit-text { margin: 6px 0 0; padding: 6px 10px; background: #f1f5f9; border-radius: 6px; font-size: 13px; line-height: 1.6; }
</style>
