<template>
  <section class="page" data-module="web_sample">
    <header class="page-head">
      <div>
        <h2>网页样本匹配与缺项校验</h2>
        <p class="page-desc">
          对解析缓存样本建正文/标题匹配索引，剔除导航页脚后按实际命中区间检索历史页面；
          选取样本逐字段校验标题缺漏与正文截断，结论带原始出处并留痕，可改选重做。
        </p>
      </div>
    </header>

    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 样本检索 -->
    <div v-if="activeTab === 'search'" class="tab-panel">
      <section class="pending-box">
        <h3>待校验新抓页面</h3>
        <div class="pending-grid">
          <label class="modal-field">
            <span>页面标题</span>
            <input v-model="pendingTitle" type="text" />
          </label>
          <label class="modal-field">
            <span>采集时间</span>
            <input :value="pendingPage.采集时间" type="text" readonly />
          </label>
          <label class="modal-field full">
            <span>正文片段（导航/页脚在打分前自动剔除）</span>
            <textarea v-model="pendingBody" rows="5"></textarea>
          </label>
        </div>
        <div class="pending-actions">
          <button class="btn primary" type="button" :disabled="loading" @click="runSearch('score')">按命中分值检索</button>
          <button class="btn" type="button" :disabled="loading" @click="runSearch('captured_at')">按采集时间检索</button>
          <button class="btn ghost" type="button" @click="reloadPending">恢复当前新抓页面</button>
          <button class="btn ghost" type="button" @click="savePending">保存修改后的新抓页面</button>
        </div>
      </section>

      <ConflictBanner :conflict="searchResult?.conflict ?? null" />

      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

      <table v-if="searchResult" class="data-table match-table">
        <thead>
          <tr>
            <th>历史样本</th>
            <th>版本类型</th>
            <th>采集时间</th>
            <th>正文命中</th>
            <th>标题命中</th>
            <th>综合分值</th>
            <th>实际命中区间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in searchResult.items" :key="item.sample_id">
            <td>
              <button class="link" type="button" @click="openSample(item.sample_id)">{{ item.sample_code }}</button>
            </td>
            <td>{{ item.version_label }}</td>
            <td>{{ item.captured_at }}</td>
            <td>{{ formatScore(item.body_score) }}</td>
            <td>{{ formatScore(item.title_score) }}</td>
            <td><strong>{{ formatScore(item.score) }}</strong></td>
            <td class="hit-count">
              <span>标题 {{ item.title_hits.length }} 段</span>
              <span>正文 {{ item.body_hits.length }} 段</span>
            </td>
            <td class="row-actions">
              <button class="btn primary small" type="button" @click="startReview(item.sample_id)">发起缺项校验</button>
            </td>
          </tr>
          <tr v-if="!searchResult.items.length">
            <td colspan="8" class="empty-state">没有匹配到历史样本，可更换正文片段后重试</td>
          </tr>
        </tbody>
      </table>

      <article v-for="item in expandedHits" :key="`hits-${item.sample_id}`" class="hits-panel">
        <h4>{{ item.sample_code }} · {{ item.version_label }} 的实际命中区间</h4>
        <HitList :hits="[...item.title_hits, ...item.body_hits]" />
      </article>
    </div>

    <!-- 历史样本库 -->
    <div v-else-if="activeTab === 'samples'" class="tab-panel">
      <table class="data-table">
        <thead>
          <tr>
            <th>样本编号</th>
            <th>版本类型</th>
            <th>页面标题</th>
            <th>采集时间</th>
            <th>小节</th>
            <th>正文字数</th>
            <th>原文</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sample in samples" :key="sample.id">
            <td>{{ sample.样本编号 }}</td>
            <td>{{ sample.版本类型 }}</td>
            <td>{{ sample.页面标题 }}</td>
            <td>{{ sample.采集时间 }}</td>
            <td>
              <span v-for="heading in sample.小节标题" :key="heading" class="seg-chip">{{ heading }}</span>
            </td>
            <td>{{ sample.正文字数 }}</td>
            <td><button class="link" type="button" @click="openSample(sample.id)">查看原文</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 复核留痕 -->
    <div v-else class="tab-panel">
      <p v-if="!reviews.length" class="empty-state">暂无复核记录，先到「样本检索」发起缺项校验</p>
      <ReviewPanel
        v-for="review in reviews"
        :key="review.id"
        class="review-item"
        :review="review"
        @recrawl="onRecrawl"
        @rechoose="switchTab('search')"
      />
    </div>

    <!-- 样本原文弹窗 -->
    <Teleport to="body">
      <div v-if="sampleDetail" class="modal-overlay" @click.self="sampleDetail = null">
        <div class="modal-card wide">
          <header class="modal-head">
            <h3>{{ sampleDetail.样本编号 }} · 原文</h3>
            <button class="btn ghost" type="button" @click="sampleDetail = null">&times;</button>
          </header>
          <div class="modal-body">
            <p><strong>页面标题：</strong>{{ sampleDetail.页面标题 }}</p>
            <p><strong>来源网址：</strong>{{ sampleDetail.来源网址 }}</p>
            <p><strong>采集时间：</strong>{{ sampleDetail.采集时间 }} · <strong>版本：</strong>{{ sampleDetail.版本类型 }}</p>
            <h4>正文小节（已去导航/页脚）</h4>
            <article v-for="seg in sampleDetail.小节" :key="seg.seg_id" class="seg-block">
              <h5>{{ seg.heading }}</h5>
              <p>{{ seg.text }}</p>
            </article>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  createReview,
  fetchPendingPage,
  fetchReviews,
  fetchSampleDetail,
  fetchSamples,
  savePendingPage,
  searchPending,
  updateDecision,
  type MatchItem,
  type ReviewRecord,
  type SampleDetail,
  type SampleSummary,
  type SearchResponse,
} from '@/api/webSample'
import ConflictBanner from './ConflictBanner.vue'
import HitList from './HitList.vue'
import ReviewPanel from './ReviewPanel.vue'

const tabs = [
  { key: 'search', label: '样本检索' },
  { key: 'samples', label: '历史样本库' },
  { key: 'reviews', label: '复核留痕' },
] as const

type TabKey = (typeof tabs)[number]['key']

const activeTab = ref<TabKey>('search')
const loading = ref(false)
const errorMessage = ref('')
const pendingPage = ref<Record<string, string>>({})
const pendingTitle = ref('')
const pendingBody = ref('')
const searchResult = ref<SearchResponse | null>(null)
const samples = ref<SampleSummary[]>([])
const reviews = ref<ReviewRecord[]>([])
const sampleDetail = ref<SampleDetail | null>(null)
const expandedHits = ref<MatchItem[]>([])

function formatScore(value: number): string {
  return (value * 100).toFixed(1) + '%'
}

async function reloadPending() {
  pendingPage.value = await fetchPendingPage()
  pendingTitle.value = pendingPage.value.页面标题 ?? ''
  pendingBody.value = pendingPage.value.正文 ?? ''
}

async function runSearch(sortBy: 'score' | 'captured_at') {
  loading.value = true
  errorMessage.value = ''
  try {
    searchResult.value = await searchPending(sortBy)
    expandedHits.value = searchResult.value.items
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样本检索失败'
  } finally {
    loading.value = false
  }
}

async function savePending() {
  errorMessage.value = ''
  try {
    await savePendingPage({ 页面标题: pendingTitle.value, 正文: pendingBody.value })
    await reloadPending()
    await runSearch('score')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存新抓页面失败'
  }
}

async function openSample(id: number) {
  sampleDetail.value = await fetchSampleDetail(id)
}

async function startReview(sampleId: number) {
  errorMessage.value = ''
  try {
    const result = await createReview(sampleId, {})
    if (!result.ok) throw new Error(result.message)
    await loadReviews()
    activeTab.value = 'reviews'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发起缺项校验失败'
  }
}

async function onRecrawl(review: ReviewRecord) {
  await updateDecision(review.id, { 处置决定: '回站点补抓', 复核备注: '复核确认需回站点补抓' })
  await loadReviews()
}

async function loadReviews() {
  const data = await fetchReviews()
  reviews.value = data.items
}

async function loadSamples() {
  const data = await fetchSamples()
  samples.value = data.items
}

function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'reviews') void loadReviews()
  if (key === 'samples') void loadSamples()
}

onMounted(async () => {
  await reloadPending()
  await runSearch('score')
})
</script>

<style scoped>
.tab-bar { display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.tab-btn { border: none; background: none; padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab-btn.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.pending-box, .hits-panel { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin-bottom: 14px; }
.pending-box h3, .hits-panel h4 { margin: 0 0 10px; font-size: 15px; }
.pending-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.modal-field { display: flex; flex-direction: column; gap: 4px; }
.modal-field.full { grid-column: 1 / -1; }
.modal-field span { font-size: 12px; color: var(--muted); }
.modal-field input, .modal-field textarea { padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; font-family: inherit; }
.pending-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.match-table td { vertical-align: top; }
.hit-count { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.hits-panel { background: #fbfdff; }
.btn.small { padding: 4px 10px; font-size: 12px; }
.seg-chip { display: inline-block; background: #eef2ff; color: #3730a3; border-radius: 4px; padding: 1px 6px; font-size: 12px; margin: 1px 2px; }
.review-item { margin-bottom: 16px; }
.modal-card.wide { width: 720px; }
.seg-block { border-left: 3px solid var(--brand); padding: 4px 12px; margin: 10px 0; background: #f8fafc; border-radius: 0 6px 6px 0; }
.seg-block h5 { margin: 4px 0; font-size: 13px; }
.seg-block p { margin: 4px 0; font-size: 13px; line-height: 1.7; }
</style>
