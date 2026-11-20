"""网页样本匹配接口。

把“样本检索 → 证据冲突识别 → 选取历史样本 → 逐字段缺项校验 → 留痕/改选重做”
这条值班复核链路按 REST 风格拆开，业务判断全部落在 WebSampleService。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.web_sample import WebSampleService

router = APIRouter(prefix="/api/web-sample", tags=["网页样本匹配"])

service = WebSampleService()


class SearchPayload(BaseModel):
    页面标题: str | None = None
    正文: str | None = None
    排序方式: str = "score"  # score=按命中分值，captured_at=按采集时间


class PendingPagePayload(BaseModel):
    页面标题: str | None = None
    正文: str | None = None
    来源网址: str | None = None
    采集时间: str | None = None


class ReviewPayload(BaseModel):
    处置决定: str | None = None
    复核备注: str | None = None


class DecisionPayload(BaseModel):
    处置决定: str
    复核备注: str | None = None


@router.get("/pending-page")
def get_pending_page() -> dict[str, Any]:
    """读取当前待校验的新抓页面工作区（含去样板后的正文）。"""
    return service.get_pending_page()


@router.put("/pending-page")
def update_pending_page(payload: PendingPagePayload) -> dict[str, Any]:
    """值班员手工修正新抓页面标题/正文后重新检索、重做校验。"""
    return service.update_pending_page(payload.model_dump(exclude_none=True))


@router.get("/samples")
def list_samples() -> dict[str, Any]:
    """历史样本清单（含小节结构，不含整篇正文，原文走详情接口）。"""
    items = service.list_samples()
    return {"items": items, "total": len(items)}


@router.get("/samples/{sample_id}")
def get_sample(sample_id: int) -> dict[str, Any]:
    """读取单条历史样本原文与小节，检索结果关联原文用。"""
    sample = service.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"历史样本 {sample_id} 不存在或已归档")
    return sample


@router.post("/search")
def search(payload: SearchPayload) -> dict[str, Any]:
    """按正文片段/标题检索历史样本，只回传实际命中区间，支持两种排序。"""
    sort_by = "captured_at" if payload.排序方式 == "captured_at" else "score"
    return service.search(payload.页面标题 or "", payload.正文 or "", sort_by=sort_by)


@router.get("/search-pending")
def search_pending(
    sort_by: str = Query(default="score", description="score=命中分值，captured_at=采集时间"),
) -> dict[str, Any]:
    """直接用待校验新抓页面发起检索，进入复核页的默认入口。"""
    return service.search_pending(sort_by="captured_at" if sort_by == "captured_at" else "score")


@router.post("/samples/{sample_id}/reviews")
def create_review(sample_id: int, payload: ReviewPayload) -> dict[str, Any]:
    """从最相似（或值班员改选）的一条历史样本发起缺项校验并留痕。"""
    record, message = service.create_review(
        sample_id, decision=payload.处置决定, note=payload.复核备注
    )
    if record is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, "review": record}


@router.get("/reviews")
def list_reviews() -> dict[str, Any]:
    """历次复核结论：各自保留实际比较过的页面与命中区间。"""
    items = service.list_reviews()
    return {"items": items, "total": len(items)}


@router.get("/reviews/{review_id}")
def get_review(review_id: int) -> dict[str, Any]:
    record = service.get_review(review_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"复核记录 {review_id} 不存在")
    return record


@router.patch("/reviews/{review_id}/decision")
def update_review_decision(review_id: int, payload: DecisionPayload) -> dict[str, Any]:
    """复核人员登记处置决定（是否回站点补抓），不动原始比较证据。"""
    record, message = service.update_review_decision(
        review_id, payload.处置决定, payload.复核备注
    )
    if record is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, "review": record}
