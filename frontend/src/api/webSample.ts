/** 网页样本匹配接口封装：检索、样本原文、缺项校验与复核留痕。 */
import { request } from './client'

const BASE = '/api/web-sample'

export interface HitInterval {
  field: 'title' | 'body'
  start: number
  end: number
  text: string
  seg_id?: string
  seg_heading?: string
}

export interface MatchItem {
  sample_id: number
  sample_code: string
  version_label: string
  source_url: string
  captured_at: string
  title_score: number
  body_score: number
  score: number
  title_hits: HitInterval[]
  body_hits: HitInterval[]
}

export interface ConflictInfo {
  conflict: boolean
  title_best: MatchItem
  body_best: MatchItem
  message: string
}

export interface SearchResponse {
  query: Record<string, string | number>
  total: number
  items: MatchItem[]
  conflict: ConflictInfo | null
}

export interface SampleSummary {
  id: number
  样本编号: string
  版本类型: string
  来源网址: string
  采集时间: string
  页面标题: string
  关联规则: string
  小节数: number
  小节标题: string[]
  正文字数: number
}

export interface FieldCheck {
  字段: string
  校验结果: string
  相似度?: number
  新页面取值: string
  参照取值: string
  原始出处: {
    sample_id: number
    样本编号: string
    版本类型: string
    来源网址: string
    采集时间: string
  }
  命中区间: HitInterval[]
  说明: string
}

export interface ReviewRecord {
  id: number
  复核编号: string
  创建时间: string
  新抓页面: Record<string, string>
  参照历史页面: Record<string, string | number>
  匹配证据: MatchItem
  证据冲突: ConflictInfo | null
  字段校验: FieldCheck[]
  系统建议: string
  处置决定: string
  复核备注: string
}

export function fetchPendingPage(): Promise<Record<string, string>> {
  return request(`${BASE}/pending-page`).then((r) => r.json())
}

export function savePendingPage(values: Record<string, string>): Promise<Record<string, string>> {
  return request(`${BASE}/pending-page`, { method: 'PUT', body: JSON.stringify(values) }).then((r) => r.json())
}

export function fetchSamples(): Promise<{ items: SampleSummary[]; total: number }> {
  return request(`${BASE}/samples`).then((r) => r.json())
}

export interface SampleSegment {
  seg_id: string
  heading: string
  text: string
  start: number
  end: number
}

export interface SampleDetail {
  id: number
  样本编号: string
  版本类型: string
  来源网址: string
  采集时间: string
  页面标题: string
  关联规则: string
  正文: string
  正文_去样板: string
  小节: SampleSegment[]
}

export function fetchSampleDetail(id: number): Promise<SampleDetail> {
  return request(`${BASE}/samples/${id}`).then((r) => r.json())
}

export function searchPending(sortBy: 'score' | 'captured_at'): Promise<SearchResponse> {
  return request(`${BASE}/search-pending?sort_by=${sortBy}`).then((r) => r.json())
}

export function searchByFragment(payload: {
  页面标题?: string
  正文?: string
  排序方式: string
}): Promise<SearchResponse> {
  return request(`${BASE}/search`, { method: 'POST', body: JSON.stringify(payload) }).then((r) => r.json())
}

export function createReview(
  sampleId: number,
  payload: { 处置决定?: string; 复核备注?: string },
): Promise<{ ok: boolean; message: string; review: ReviewRecord }> {
  return request(`${BASE}/samples/${sampleId}/reviews`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }).then((r) => r.json())
}

export function fetchReviews(): Promise<{ items: ReviewRecord[]; total: number }> {
  return request(`${BASE}/reviews`).then((r) => r.json())
}

export function updateDecision(
  reviewId: number,
  payload: { 处置决定: string; 复核备注?: string },
): Promise<{ ok: boolean; message: string; review: ReviewRecord }> {
  return request(`${BASE}/reviews/${reviewId}/decision`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }).then((r) => r.json())
}
