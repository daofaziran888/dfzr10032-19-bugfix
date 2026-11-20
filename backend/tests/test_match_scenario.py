"""网页样本匹配链路行为自测：纯标准库，python -I 运行。

覆盖需求关键点：
1. 去样板后，共享导航/页脚的无关公告不会靠样板文字排到前面；
2. 标题命中镜像原版、正文命中修订稿时能识别证据冲突；
3. 从最相似的修订稿发起校验，能检出标题缺漏与正文截断；
4. 改选镜像原版重做校验，能检出“停航日期”段落缺失，两份结论各自留痕；
5. 命中区间只包含实际命中的文字，且能映射回正文小节。
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/workspace/backend")

from app.services import matchlib
from app.seed_samples import PENDING_PAGE, WEB_SAMPLE_ROWS

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("PASS" if condition else "FAIL"), "-", message)
    if not condition:
        failures.append(message)


def sample_by_label(label: str) -> dict:
    return next(row for row in WEB_SAMPLE_ROWS if row["版本类型"] == label)


mirror = sample_by_label("镜像原版（保留旧标题）")
revised = sample_by_label("正文修订版")
full = sample_by_label("补抓完整版")
weather = sample_by_label("常规公告")

# 1. 样板剔除：导航/页脚整行被删掉，正文保留。
cleaned = matchlib.strip_boilerplate(str(mirror["正文"]))
check("首页 机构简介" not in cleaned, "导航栏在打分前已剔除")
check("版权所有" not in cleaned and "ICP备案" not in cleaned, "页脚在打分前已剔除")
check("停航原因" in cleaned and "海巡艇" in cleaned, "正文内容在去样板后保留")

# 2. 检索排序：修订稿正文最相似，天气公告不会因共享导航/页脚排前面。
results = matchlib.rank_samples(
    WEB_SAMPLE_ROWS, PENDING_PAGE["页面标题"], PENDING_PAGE["正文"]
)
order = [item.sample_id for item in results]
print("    排序（按命中分值）：", [(r.sample_code, round(r.body_score, 3), round(r.score, 3)) for r in results])
check(results[0].sample_id == revised["id"], "正文修订稿凭正文实际命中排第一（最相似一条）")
check(weather["id"] not in order, "共享导航/页脚的无关大雾公告被弱匹配阈值过滤，不进入检索结果")
check(order.index(revised["id"]) < order.index(mirror["id"]), "正文命中的修订稿排在只命中旧标题的镜像原版之前")

# 3. 证据冲突：标题最相似是镜像，正文最相似是修订稿。
conflict = matchlib.detect_conflict(results)
check(conflict is not None, "识别出标题/正文两处证据冲突")
if conflict:
    check(conflict["title_best"]["sample_id"] == mirror["id"], "标题证据指向镜像原版")
    check(conflict["body_best"]["sample_id"] == revised["id"], "正文证据指向修订稿")

# 4. 命中区间只含实际命中文字，并能映射到小节。
revised_match = next(item for item in results if item.sample_id == revised["id"])
body_hit_texts = "".join(hit.text for hit in revised_match.body_hits)
check(all("版权所有" not in hit.text for hit in revised_match.body_hits), "命中区间不含页脚样板文字")
check(any(hit.seg_heading and "停航日期" in hit.seg_heading for hit in revised_match.body_hits), "正文命中区间可定位到「停航日期」小节")
check("停航时段为2026年9月10日" in body_hit_texts, "命中区间包含真实正文片段")
check(all(hit.field == "title" for hit in revised_match.title_hits), "标题命中区间与正文命中区间分开返回")

# 5. 采集时间排序可用。
by_time = matchlib.rank_samples(
    WEB_SAMPLE_ROWS, PENDING_PAGE["页面标题"], PENDING_PAGE["正文"], sort_by="captured_at"
)
check(by_time[0].sample_id == full["id"], "按采集时间排序时最新的补抓完整版排第一")

# 6. 用服务层做逐字段校验（需要 FastAPI 之外的纯服务可独立运行）。
from app.services.web_sample import WebSampleService  # noqa: E402

svc = WebSampleService()

review_revised, _ = svc.create_review(revised["id"], decision="回站点补抓", note="正文截断需补抓")
check(review_revised is not None, "从最相似的修订稿发起缺项校验成功")
statuses_revised = {c["字段"]: c["校验结果"] for c in review_revised["字段校验"]}
print("    修订稿校验结果：", statuses_revised)
check(statuses_revised.get("页面标题") == "标题缺漏", "检出新页面标题缺漏（旧镜像标题 vs 修订稿标题）")
truncated = [c for c in review_revised["字段校验"] if c["校验结果"] == "正文截断"]
check(len(truncated) == 1 and "注意事项" in truncated[0]["字段"], "检出「注意事项」小节正文截断")
check(review_revised["系统建议"] == "建议回站点补抓", "系统给出回站点补抓建议")
check(review_revised["处置决定"] == "回站点补抓", "复核人员的补抓决定被记录")
# 每条字段结论都带原始出处与实际命中区间。
for check_item in review_revised["字段校验"]:
    check("原始出处" in check_item and check_item["原始出处"]["sample_id"] == revised["id"],
          f"字段「{check_item['字段']}」结论带修订稿原始出处")
    if check_item["命中区间"]:
        check(all(set(hit) >= {"field", "start", "end", "text"} for hit in check_item["命中区间"]),
              f"字段「{check_item['字段']}」只回传实际命中区间结构")

# 7. 改选镜像原版重做：镜像没有“停航日期”，应判段落缺失；两份结论并存。
review_mirror, _ = svc.create_review(mirror["id"], decision="维持镜像结论", note="改选镜像原版复核")
statuses_mirror = {c["字段"]: c["校验结果"] for c in review_mirror["字段校验"]}
print("    镜像版校验结果：", statuses_mirror)
missing_seg = [c for c in review_mirror["字段校验"] if c["校验结果"] == "正文截断"]
check(any("注意事项" in c["字段"] for c in missing_seg),
      "镜像原版比对同样检出新页面「注意事项」正文截断并提示补抓")
extra_seg = [c for c in review_mirror["字段校验"] if c["校验结果"] == "参照样本无此小节"]
check(any("停航日期" in c["字段"] for c in extra_seg), "新页面多出的「停航日期」在镜像比对中标注为参照样本无此小节")
check(review_mirror["参照历史页面"]["sample_id"] == mirror["id"], "第二份结论记录的是镜像原版这一页")
check(review_revised["id"] != review_mirror["id"], "改选重做生成独立复核编号，两份结论各自留痕")

reviews = svc.list_reviews()
check(len(reviews) == 2, "两次复核都已留痕，可回看各自比较过的页面与命中区间")
compared_ids = {r["参照历史页面"]["sample_id"] for r in reviews}
check(compared_ids == {mirror["id"], revised["id"]}, "留痕记录分别指向实际比较过的两份历史页面")

# 7.1 真·整段缺失：补抓完整版含「恢复通航」，新抓页面完全没有这一小节。
review_full, _ = svc.create_review(full["id"])
full_missing = [c for c in review_full["字段校验"] if c["校验结果"] == "段落缺失"]
check(any("恢复通航" in c["字段"] and not c["命中区间"] for c in full_missing),
      "新抓页面完全没有「恢复通航」小节，判为段落缺失且无命中区间")
check(review_full["系统建议"] == "建议回站点补抓", "存在段落缺失时同样建议回站点补抓")

# 8. 样本详情能关联原文与小节。
detail = svc.get_sample(mirror["id"])
headings = [seg["heading"] for seg in detail["小节"]]
check("二、停航日期" not in headings, "镜像原版原文确认没有「停航日期」小节")
check("二、停航日期" in [seg["heading"] for seg in svc.get_sample(revised["id"])["小节"]],
      "修订稿原文确认含「停航日期」小节")

print()
if failures:
    print(f"共 {len(failures)} 项失败：")
    for item in failures:
        print(" -", item)
    raise SystemExit(1)
print("全部行为检查通过")
