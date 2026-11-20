<template>
  <div v-if="conflict" class="conflict-banner">
    <div class="conflict-head">
      <span class="conflict-badge">证据冲突</span>
      <strong>{{ conflict.message }}</strong>
    </div>
    <div class="conflict-columns">
      <div class="conflict-side title-side">
        <span class="side-label">标题证据</span>
        <p>{{ conflict.title_best.version_label }}（{{ conflict.title_best.sample_code }}）</p>
        <small>标题相似度 {{ formatScore(conflict.title_best.title_score) }}</small>
      </div>
      <div class="conflict-arrow">→</div>
      <div class="conflict-side body-side">
        <span class="side-label">正文证据</span>
        <p>{{ conflict.body_best.version_label }}（{{ conflict.body_best.sample_code }}）</p>
        <small>正文相似度 {{ formatScore(conflict.body_best.body_score) }}</small>
      </div>
    </div>
    <p class="conflict-hint">
      值班员默认从正文最相似的「{{ conflict.body_best.version_label }}」发起缺项校验，也可在下方改选镜像原版重做。
    </p>
  </div>
</template>

<script setup lang="ts">
import type { ConflictInfo } from '@/api/webSample'

defineProps<{ conflict: ConflictInfo | null }>()

function formatScore(value: number): string {
  return (value * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.conflict-banner { border: 1px solid #f59e0b; background: #fffbeb; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; }
.conflict-head { display: flex; gap: 8px; align-items: center; }
.conflict-badge { background: #d97706; color: #fff; font-size: 12px; border-radius: 4px; padding: 2px 8px; }
.conflict-columns { display: grid; grid-template-columns: 1fr 40px 1fr; gap: 10px; margin-top: 10px; align-items: center; }
.conflict-side { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
.conflict-side p { margin: 4px 0; font-size: 13px; }
.side-label { font-size: 12px; color: var(--muted); }
.title-side { border-top: 3px solid #7c3aed; }
.body-side { border-top: 3px solid #0f766e; }
.conflict-arrow { text-align: center; color: var(--muted); font-size: 18px; }
.conflict-hint { margin: 10px 0 0; font-size: 12px; color: #92400e; }
</style>
