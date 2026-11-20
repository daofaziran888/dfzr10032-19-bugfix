"""网页样本匹配核心算法。

只依赖标准库，负责：

1. 去掉导航、页脚等样板文字，避免多篇公告因同一段站点导航被排到前面；
2. 基于正文片段做字符级 shingle（n-gram）建索引，计算 Jaccard 匹配分值；
3. 用 SequenceMatcher 抽出“当时实际命中的文字区间”，检索与复核都只回传这些区间；
4. 分别给出标题命中与正文命中，识别两处证据指向不同历史页面的冲突。

这里不碰任何 HTTP/状态对象，方便用 ``python -I`` 直接做算法自测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

# 字符级 shingle 长度：中文公告按 3 字一组，兼顾短语区分度与少量改写容错。
SHINGLE_SIZE = 3
# 命中区间最短长度，短于该长度的碎片不作为“实际命中区间”展示。
MIN_HIT_LEN = 6
# 低于该 Jaccard 分值的候选直接不返回，防止样板词造成的弱匹配占位。
MIN_SCORE = 0.06

# 站点通用样板：导航栏与页脚。多个页面共享这些文字，匹配前必须剔除。
BOILERPLATE_TERMS: tuple[str, ...] = (
    "首页",
    "机构简介",
    "政务公开",
    "通知公告",
    "政策法规",
    "办事服务",
    "联系我们",
    "网站地图",
    "版权所有",
    "主办单位",
    "ICP备案",
    "本站支持IPv6",
    "扫码关注公众号",
    "地址：",
    "邮编：",
    "电话：",
    "您是本站第",
    "位访客",
)


@dataclass
class Segment:
    """正文里的一个自然段/小节，保留在正文中的字符区间，便于逐段定位。"""

    seg_id: str
    heading: str
    text: str
    start: int
    end: int


@dataclass
class HitInterval:
    """一段实际命中的文字区间（相对所属文本的字符偏移）。"""

    field: str  # title / body
    start: int
    end: int
    text: str
    seg_id: str | None = None
    seg_heading: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "field": self.field,
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }
        if self.seg_id is not None:
            data["seg_id"] = self.seg_id
            data["seg_heading"] = self.seg_heading
        return data


@dataclass
class MatchResult:
    """新页面对一条历史样本的匹配结果。"""

    sample_id: int
    sample_code: str
    version_label: str
    source_url: str
    captured_at: str
    title_score: float
    body_score: float
    score: float
    title_hits: list[HitInterval] = field(default_factory=list)
    body_hits: list[HitInterval] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "sample_code": self.sample_code,
            "version_label": self.version_label,
            "source_url": self.source_url,
            "captured_at": self.captured_at,
            "title_score": round(self.title_score, 4),
            "body_score": round(self.body_score, 4),
            "score": round(self.score, 4),
            "title_hits": [hit.to_dict() for hit in self.title_hits],
            "body_hits": [hit.to_dict() for hit in self.body_hits],
        }


def normalize_text(text: str) -> str:
    """折叠空白，统一全角/半角标点差异，保证偏移仍基于原始文本计算。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t　]+", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def strip_boilerplate(text: str) -> str:
    """删除导航、页脚样板行：命中样板词的整行剔除，其余正文原样保留。

    公告正文可能合法出现“公告”等词，因此只按整行/整段包含样板特征来删，
    不做全文子串抹除，避免误伤正文。
    """
    cleaned_lines: list[str] = []
    for line in normalize_text(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        hit_terms = sum(1 for term in BOILERPLATE_TERMS if term in line)
        # 一行里出现两个及以上样板词，或整行就是导航/页脚短句，判为样板。
        if hit_terms >= 2 or line in BOILERPLATE_TERMS:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def normalize_heading(heading: str) -> str:
    """去掉小节标题前的中文/数字序号，保留语义标题。

    修订稿插入“停航日期”后后续小节序号整体后移（三、注意事项 → 四、注意事项），
    按完整标题匹配会把同一小节误判成缺失，因此比对前先剥离序号。
    """
    return re.sub(r"^(?:[一二三四五六七八九十]+|\d+)[、.．]\s*", "", heading.strip())


def build_segments(body: str) -> list[Segment]:
    """把正文切成带标题的小节；无小节标题时整体作为一个正文段。"""
    body = normalize_text(body)
    lines = body.split("\n")
    segments: list[Segment] = []
    current_heading = "正文"
    buffer: list[str] = []
    cursor = 0

    def flush(heading: str, buf: list[str], start: int) -> None:
        if not buf:
            return
        text = "\n".join(buf)
        segments.append(
            Segment(
                seg_id=f"S{len(segments) + 1:02d}",
                heading=heading,
                text=text,
                start=start,
                end=start + len(text),
            )
        )

    seg_start = 0
    for line in lines:
        # 形如“一、停航日期”“二、通航安排”的小节标题。
        if re.match(r"^[一二三四五六七八九十]+、", line) and len(line) <= 20:
            flush(current_heading, buffer, seg_start)
            current_heading = line
            buffer = []
            seg_start = cursor
        else:
            if not buffer:
                seg_start = cursor
            buffer.append(line)
        cursor += len(line) + 1  # 加回被 split 掉的换行符
    flush(current_heading, buffer, seg_start)
    if not segments:
        segments.append(Segment("S01", "正文", body, 0, len(body)))
    return segments


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    """字符级 n-gram 集合，用作 Jaccard 的索引项。"""
    text = normalize_text(text)
    if len(text) < size:
        return {text} if text else set()
    return {text[i : i + size] for i in range(len(text) - size + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    union = len(left | right)
    return overlap / union if union else 0.0


def actual_hits(query: str, target: str, field: str, segments: list[Segment] | None = None) -> list[HitInterval]:
    """用最长公共块抽取“目标文本中被查询实际命中的区间”。

    只回传命中的文字与偏移，不回传目标全文——复核界面只能展示当时命中的片段。
    正文区间会映射回所属小节，方便定位“停航日期”这类段落。
    """
    query = normalize_text(query)
    target = normalize_text(target)
    if not query or not target:
        return []
    matcher = SequenceMatcher(a=query, b=target, autojunk=False)
    hits: list[HitInterval] = []
    for block in matcher.get_matching_blocks():
        # block.b / block.size 是目标文本 target 上的偏移与长度。
        if block.size < MIN_HIT_LEN:
            continue
        start, end = block.b, block.b + block.size
        text = target[start:end]
        seg_id = seg_heading = None
        if field == "body" and segments:
            # 一个命中块可能横跨多个相邻小节，取首个覆盖到的小节归属；
            # 完整的逐小节归属在服务层按小节单独抽取，这里只做整体定位。
            for seg in segments:
                if seg.start <= start < seg.end or (start < seg.start < end):
                    seg_id, seg_heading = seg.seg_id, seg.heading
                    break
            # 横跨多小节时在文本里标出全部命中的小节标题，避免漏标。
            crossed = [seg.heading for seg in segments if start < seg.end and end > seg.start]
            if len(crossed) > 1:
                seg_heading = " / ".join(crossed)
        hits.append(HitInterval(field, start, end, text, seg_id, seg_heading))
    return hits


def _segment_for_offset(segments: list[Segment], start: int) -> Segment | None:
    for seg in segments:
        if seg.start <= start < seg.end:
            return seg
    return None


def score_pair(
    sample: dict[str, Any],
    query_title: str,
    query_body: str,
) -> MatchResult:
    """计算新页面与单条历史样本之间的标题/正文匹配。"""
    sample_title = normalize_text(str(sample.get("页面标题", "")))
    sample_body_clean = strip_boilerplate(str(sample.get("正文", "")))
    sample_segments = build_segments(sample_body_clean)

    query_title_n = normalize_text(query_title)
    query_body_clean = strip_boilerplate(query_body)

    title_score = jaccard(shingles(query_title_n), shingles(sample_title))
    body_score = jaccard(shingles(query_body_clean), shingles(sample_body_clean))
    # 正文信息量大、权重更高；标题只做辅助，避免同标题不同版本互相顶替。
    total_score = body_score * 0.75 + title_score * 0.25

    title_hits = actual_hits(query_title_n, sample_title, "title")
    body_hits = actual_hits(query_body_clean, sample_body_clean, "body", sample_segments)

    return MatchResult(
        sample_id=int(sample["id"]),
        sample_code=str(sample.get("样本编号", "")),
        version_label=str(sample.get("版本类型", "")),
        source_url=str(sample.get("来源网址", "")),
        captured_at=str(sample.get("采集时间", "")),
        title_score=title_score,
        body_score=body_score,
        score=total_score,
        title_hits=title_hits,
        body_hits=body_hits,
    )


def rank_samples(
    samples: list[dict[str, Any]],
    query_title: str,
    query_body: str,
    *,
    sort_by: str = "score",
    limit: int = 20,
) -> list[MatchResult]:
    """对全部历史样本打分并排序，支持按命中分值或采集时间排序。

    命中分值模式下以正文实际命中相似度为主键（标题只作次级参照），
    保证“同标题的旧镜像”不会压过“正文真正命中的修订稿”。
    """
    results = [score_pair(sample, query_title, query_body) for sample in samples]
    results = [item for item in results if item.score >= MIN_SCORE or item.title_score >= MIN_SCORE]
    if sort_by == "captured_at":
        results.sort(key=lambda item: item.captured_at, reverse=True)
    else:
        results.sort(key=lambda item: (item.body_score, item.score), reverse=True)
    return results[:limit]


def detect_conflict(results: list[MatchResult]) -> dict[str, Any] | None:
    """标题最相似与正文最相似指向不同样本时，给出证据冲突说明。"""
    body_best = max(results, key=lambda item: item.body_score, default=None)
    title_best = max(results, key=lambda item: item.title_score, default=None)
    if body_best is None or title_best is None:
        return None
    if body_best.sample_id == title_best.sample_id:
        return None
    return {
        "conflict": True,
        "title_best": title_best.to_dict(),
        "body_best": body_best.to_dict(),
        "message": (
            f"标题命中{title_best.version_label}（{title_best.sample_code}），"
            f"正文命中{body_best.version_label}（{body_best.sample_code}），两处证据指向不同历史页面"
        ),
    }
