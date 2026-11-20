<template>
  <div class="review-panel">
    <header class="review-head">
      <div>
        <h3>{{ review.复核编号 }} · 缺项校验结论</h3>
        <p class="review-time">创建于 {{ review.创建时间 }}</p>
      </div>
      <span class="suggestion" :class="suggestionClass">{{ review.系统建议 }}</span>
    </header>

    <section class="source-box">
      <h4>实际比较的页面</h4>
      <div class="source-grid">
        <div>
          <span class="side-label">新抓页面</span>
          <p>{{ review.新抓页面.页面标题 }}</p>
          <small>{{ review.新抓页面.来源网址 }} · {{ review.新抓页面.采集时间 }}</small>
        </div>
        <div>
          <span class="side-label">参照历史页面（原始出处）</span>
          <p>{{ review.参照历史页面.版本类型 }}（{{ review.参照历史页面.样本编号 }}）</p>
          <small>{{ review.参照历史页面.来源网址 }} · {{ review.参照历史页面.采集时间 }}</small>
        </div>
      </div>
    </section>

    <ConflictBanner :conflict="review.证据冲突" />

    <section class="field-box">
      <h4>逐字段校验（每条结论都带原始出处与实际命中区间）</h4>
      <article v-for="(check, idx) in review.字段校验" :key="idx" class="field-card" :class="statusClass(check.校验结果)">
        <header class="field-head">
          <strong>{{ check.字段 }}</strong>
          <span class="status-tag">{{ check.校验结果 }}</span>
          <span v-if="check.相似度 !== undefined" class="similarity">相似度 {{ formatScore(check.相似度) }}</span>
        </header>
        <p class="field-detail">{{ check.说明 }}</p>
        <div class="field-values">
          <div><span class="side-label">新抓页面</span><p>{{ check.新页面取值 }}</p></div>
          <div><span class="side-label">参照原文</span><p>{{ check.参照取值 }}</p></div>
        </div>
        <div class="field-hits">
          <span class="side-label">实际命中区间（仅展示命中文字）</span>
          <HitList :hits="check.命中区间" />
        </div>
        <footer class="field-source">
          出处：{{ check.原始出处.版本类型 }} · {{ check.原始出处.样本编号 }} ·
          <a :href="String(check.原始出处.来源网址)" target="_blank" rel="noreferrer">{{ check.原始出处.来源网址 }}</a>
        </footer>
      </article>
    </section>

    <section class="decision-box">
      <h4>复核处置</h4>
      <p>当前决定：<strong>{{ review.处置决定 }}</strong>
        <span v-if="review.复核备注"> · 备注：{{ review.复核备注 }}</span>
      </p>
      <div class="decision-actions">
        <button class="btn primary" type="button" @click="emit('recrawl', review)">登记回站点补抓</button>
        <button class="btn" type="button" @click="emit('rechoose', review)">改选历史页面重做校验</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import ConflictBanner from './ConflictBanner.vue'
import HitList from './HitList.vue'
import type { ReviewRecord } from '@/api/webSample'

const props = defineProps<{ review: ReviewRecord }>()
const emit = defineEmits<{
  (e: 'recrawl', review: ReviewRecord): void
  (e: 'rechoose', review: ReviewRecord): void
}>()

function formatScore(value: number): string {
  return (value * 100).toFixed(1) + '%'
}

function statusClass(status: string): string {
  if (status === '一致') return 'is-ok'
  if (status === '正文截断' || status === '段落缺失') return 'is-bad'
  return 'is-warn'
}

function suggestionClass(): string {
  return props.review.系统建议.includes('补抓') ? 'suggest-bad' : 'suggest-ok'
}
</script>

<style scoped>
.review-panel { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.review-head { display: flex; justify-content: space-between; align-items: flex-start; }
.review-head h3 { margin: 0; font-size: 16px; }
.review-time { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
.suggestion { border-radius: 16px; padding: 4px 12px; font-size: 13px; }
.suggest-bad { background: #fef3c7; color: #92400e; }
.suggest-ok { background: #dcfce7; color: #166534; }
.source-box, .field-box, .decision-box { margin-top: 14px; }
.source-box h4, .field-box h4, .decision-box h4 { font-size: 14px; margin: 0 0 8px; }
.source-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.source-grid > div, .field-values > div { background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
.side-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.source-grid p, .field-values p { margin: 4px 0; font-size: 13px; line-height: 1.6; }
small { color: var(--muted); word-break: break-all; }
.field-card { border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 10px; }
.field-card.is-ok { border-left: 4px solid #16a34a; }
.field-card.is-bad { border-left: 4px solid #dc2626; }
.field-card.is-warn { border-left: 4px solid #d97706; }
.field-head { display: flex; gap: 10px; align-items: center; }
.status-tag { font-size: 12px; border-radius: 4px; padding: 2px 8px; background: #eef2ff; color: #3730a3; }
.is-bad .status-tag { background: #fee2e2; color: #991b1b; }
.is-warn .status-tag { background: #fef3c7; color: #92400e; }
.similarity { color: var(--muted); font-size: 12px; }
.field-detail { font-size: 13px; margin: 8px 0; }
.field-values { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.field-hits { margin-top: 8px; }
.field-source { margin-top: 8px; font-size: 12px; color: var(--muted); }
.field-source a { color: var(--brand); word-break: break-all; }
.decision-actions { display: flex; gap: 8px; }
</style>
