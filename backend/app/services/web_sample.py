"""网页样本匹配服务。

职责分三块：

1. 样本检索：对新页面标题/正文去样板后打分，按命中分值或采集时间排序，
   只回传当时实际命中的文字区间，并标出标题证据与正文证据的冲突；
2. 原文关联：按样本编号读取历史样本原文与小节结构，供复核界面回看；
3. 缺项校验：拿所选历史样本逐字段（标题、正文小节）比对新页面，
   识别标题缺漏、段落缺失、正文截断，结论带原始出处与命中区间并留痕。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import matchlib
from app.store import store

MODULE = "web_sample"
REVIEW_MODULE = "sample_review"

# 新页面小节内容短于参照小节的该比例且相似度不足时，判为正文截断。
TRUNCATION_RATIO = 0.85
SEGMENT_MATCH_SCORE = 0.45


class WebSampleService:
    # ---------- 工作区：待校验的新抓页面 ----------

    def get_pending_page(self) -> dict[str, Any]:
        page = dict(store.pending_page())
        page["正文_去样板"] = matchlib.strip_boilerplate(str(page.get("正文", "")))
        return page

    def update_pending_page(self, values: dict[str, Any]) -> dict[str, Any]:
        allowed = {k: values[k] for k in ("页面标题", "正文", "来源网址", "采集时间") if values.get(k) is not None}
        return self.get_pending_page() if not allowed else dict(store.update_pending_page(allowed))

    # ---------- 历史样本 ----------

    def list_samples(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            segments = matchlib.build_segments(matchlib.strip_boilerplate(str(row.get("正文", ""))))
            items.append(
                {
                    "id": row["id"],
                    "样本编号": row.get("样本编号"),
                    "版本类型": row.get("版本类型"),
                    "来源网址": row.get("来源网址"),
                    "采集时间": row.get("采集时间"),
                    "页面标题": row.get("页面标题"),
                    "关联规则": row.get("关联规则"),
                    "小节数": len(segments),
                    "小节标题": [seg.heading for seg in segments],
                    "正文字数": len(matchlib.normalize_text(matchlib.strip_boilerplate(str(row.get("正文", ""))))),
                }
            )
        return items

    def get_sample(self, sample_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, sample_id)
        if row is None:
            return None
        data = dict(row)
        cleaned = matchlib.strip_boilerplate(str(row.get("正文", "")))
        data["正文_去样板"] = cleaned
        data["小节"] = [
            {"seg_id": seg.seg_id, "heading": seg.heading, "text": seg.text, "start": seg.start, "end": seg.end}
            for seg in matchlib.build_segments(cleaned)
        ]
        return data

    # ---------- 样本检索（匹配索引） ----------

    def search(
        self,
        query_title: str,
        query_body: str,
        *,
        sort_by: str = "score",
    ) -> dict[str, Any]:
        samples = store.rows(MODULE)
        results = matchlib.rank_samples(samples, query_title, query_body, sort_by=sort_by)
        conflict = matchlib.detect_conflict(results)
        return {
            "query": {
                "页面标题": matchlib.normalize_text(query_title),
                "正文字数": len(matchlib.normalize_text(matchlib.strip_boilerplate(query_body))),
                "排序方式": "采集时间" if sort_by == "captured_at" else "命中分值",
            },
            "total": len(results),
            "items": [item.to_dict() for item in results],
            "conflict": conflict,
        }

    def search_pending(self, *, sort_by: str = "score") -> dict[str, Any]:
        page = store.pending_page()
        return self.search(str(page.get("页面标题", "")), str(page.get("正文", "")), sort_by=sort_by)

    # ---------- 逐字段缺项校验 ----------

    def _check_title(self, sample: dict[str, Any], new_title: str) -> dict[str, Any]:
        sample_title = matchlib.normalize_text(str(sample.get("页面标题", "")))
        new_title_n = matchlib.normalize_text(new_title)
        hits = matchlib.actual_hits(new_title_n, sample_title, "title")
        score = matchlib.jaccard(matchlib.shingles(new_title_n), matchlib.shingles(sample_title))
        if new_title_n == sample_title:
            status, detail = "一致", "新抓页面标题与参照样本标题完全一致"
        else:
            status = "标题缺漏"
            detail = (
                f"新抓页面标题与参照样本不一致：参照样本标题为《{sample_title}》，"
                f"新抓页面标题为《{new_title_n}》，可能沿用了旧版镜像标题"
            )
        return {
            "字段": "页面标题",
            "校验结果": status,
            "相似度": round(score, 4),
            "新页面取值": new_title_n,
            "参照取值": sample_title,
            "原始出处": self._source_ref(sample),
            "命中区间": [hit.to_dict() for hit in hits],
            "说明": detail,
        }

    def _check_segments(self, sample: dict[str, Any], new_body: str) -> list[dict[str, Any]]:
        sample_clean = matchlib.strip_boilerplate(str(sample.get("正文", "")))
        new_clean = matchlib.strip_boilerplate(new_body)
        sample_segments = matchlib.build_segments(sample_clean)
        new_segments = matchlib.build_segments(new_clean)
        # 按剥离序号后的语义标题配对，容忍修订导致的小节序号后移。
        new_by_heading = {matchlib.normalize_heading(seg.heading): seg for seg in new_segments}

        checks: list[dict[str, Any]] = []
        for seg in sample_segments:
            ref = self._source_ref(sample)
            paired = new_by_heading.get(matchlib.normalize_heading(seg.heading))
            if paired is None:
                checks.append(
                    {
                        "字段": f"正文小节·{seg.heading}",
                        "校验结果": "段落缺失",
                        "新页面取值": "（新抓页面未找到该小节）",
                        "参照取值": seg.text,
                        "原始出处": ref,
                        "命中区间": [],
                        "说明": f"参照样本含「{matchlib.normalize_heading(seg.heading)}」小节，新抓页面缺失，建议回站点补抓",
                    }
                )
                continue
            seg_ref = [matchlib.Segment(seg.seg_id, seg.heading, seg.text, 0, len(seg.text))]
            hits = matchlib.actual_hits(paired.text, seg.text, "body", seg_ref)
            score = matchlib.jaccard(matchlib.shingles(paired.text), matchlib.shingles(seg.text))
            length_ratio = len(paired.text) / len(seg.text) if seg.text else 1.0
            # 有实质内容重合但新页面明显更短 → 截断；几乎没有重合 → 整段缺失。
            if length_ratio < TRUNCATION_RATIO:
                status = "正文截断"
                detail = (
                    f"「{matchlib.normalize_heading(seg.heading)}」小节新抓内容长度仅为参照样本的 "
                    f"{length_ratio:.0%}（相似度 {score:.2f}），参照样本中仍有未命中的后续文字，"
                    "疑似抓取被截断，建议回站点补抓"
                )
            elif score < SEGMENT_MATCH_SCORE:
                status = "段落缺失"
                detail = (
                    f"「{matchlib.normalize_heading(seg.heading)}」小节内容与参照样本相似度仅 "
                    f"{score:.2f}，疑似未采到"
                )
            else:
                status = "一致"
                detail = f"「{matchlib.normalize_heading(seg.heading)}」小节内容与参照样本一致（相似度 {score:.2f}）"
            checks.append(
                {
                    "字段": f"正文小节·{seg.heading}",
                    "校验结果": status,
                    "相似度": round(score, 4),
                    "新页面取值": paired.text,
                    "参照取值": seg.text,
                    "原始出处": ref,
                    "命中区间": [hit.to_dict() for hit in hits],
                    "说明": detail,
                }
            )

        # 新页面多出、参照样本没有的小节（例如拿镜像原版比对时，新页面的“停航日期”）。
        sample_headings = {matchlib.normalize_heading(seg.heading) for seg in sample_segments}
        for seg in new_segments:
            if matchlib.normalize_heading(seg.heading) not in sample_headings:
                checks.append(
                    {
                        "字段": f"正文小节·{seg.heading}",
                        "校验结果": "参照样本无此小节",
                        "新页面取值": seg.text,
                        "参照取值": "（参照样本不含该小节）",
                        "原始出处": self._source_ref(sample),
                        "命中区间": [],
                        "说明": (
                            f"新抓页面含「{matchlib.normalize_heading(seg.heading)}」小节，"
                            f"但所选{sample.get('版本类型', '')}不含该小节，"
                            "证据可能来自更新的修订版本，可改选其他历史页面重做校验"
                        ),
                    }
                )
        return checks

    def _source_ref(self, sample: dict[str, Any]) -> dict[str, Any]:
        """每条字段结论都带原始出处，复核时可追溯到具体历史页面。"""
        return {
            "sample_id": int(sample["id"]),
            "样本编号": sample.get("样本编号"),
            "版本类型": sample.get("版本类型"),
            "来源网址": sample.get("来源网址"),
            "采集时间": sample.get("采集时间"),
        }

    def create_review(
        self,
        sample_id: int,
        *,
        decision: str | None = None,
        note: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        sample = store.find(MODULE, sample_id)
        if sample is None:
            return None, f"历史样本 {sample_id} 不存在，无法发起缺项校验"
        page = store.pending_page()
        new_title, new_body = str(page.get("页面标题", "")), str(page.get("正文", ""))

        match = matchlib.score_pair(sample, new_title, new_body)
        all_results = matchlib.rank_samples(store.rows(MODULE), new_title, new_body)
        conflict = matchlib.detect_conflict(all_results)

        field_checks = [self._check_title(sample, new_title), *self._check_segments(sample, new_body)]
        bad_statuses = {"正文截断", "段落缺失"}
        has_truncation = any(check["校验结果"] in bad_statuses for check in field_checks)
        has_title_gap = any(check["校验结果"] == "标题缺漏" for check in field_checks)
        if has_truncation:
            suggestion = "建议回站点补抓"
        elif has_title_gap:
            suggestion = "建议核对标题来源后再入库"
        else:
            suggestion = "校验通过，可入库"

        review_id = store.next_id(REVIEW_MODULE)
        record = {
            "id": review_id,
            "复核编号": f"REV-{review_id:04d}",
            "创建时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "新抓页面": {
                "来源网址": page.get("来源网址"),
                "采集时间": page.get("采集时间"),
                "页面标题": matchlib.normalize_text(new_title),
            },
            "参照历史页面": self._source_ref(sample),
            "匹配证据": match.to_dict(),
            "证据冲突": conflict,
            "字段校验": field_checks,
            "系统建议": suggestion,
            "处置决定": decision or suggestion,
            "复核备注": note or "",
        }
        store.rows(REVIEW_MODULE).append(record)
        return record, "复核结论已生成并留痕"

    def list_reviews(self) -> list[dict[str, Any]]:
        return list(reversed(store.rows(REVIEW_MODULE)))

    def get_review(self, review_id: int) -> dict[str, Any] | None:
        return store.find(REVIEW_MODULE, review_id)

    def update_review_decision(
        self, review_id: int, decision: str, note: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        record = store.find(REVIEW_MODULE, review_id)
        if record is None:
            return None, f"复核记录 {review_id} 不存在"
        record["处置决定"] = decision
        if note is not None:
            record["复核备注"] = note
        return record, "复核处置已更新"
