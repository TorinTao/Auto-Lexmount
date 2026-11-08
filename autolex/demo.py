"""Trusted, deterministic fixtures. Never evidence of a real API run."""
from .common import now

CODE = '''import json
from pathlib import Path
data = json.loads(Path("input.json").read_text())
for page in data["pages"]:
    page["result"]["main_text"] = " ".join(page["result"]["main_text"].split())
if not data["pages"] or len({p["url"] for p in data["pages"]}) != len(data["pages"]) or any("Use Lexmount cloud." not in p["result"]["main_text"] for p in data["pages"]):
    raise ValueError("EVIDENCE_ERROR: missing fixture source evidence")
items = [{"title": p["result"].get("title", "Untitled"), "url": p["url"],
          "summary": p["result"]["main_text"][:400]} for p in data["pages"]]
Path("output.json").write_text(json.dumps({"items": items}, ensure_ascii=False))
'''


class DemoFetch:
    def fetch(self, url):
        return {"url": url, "provider": "fixture", "demo": True, "fetched_at": now(),
                "request_id": None, "result": {"title": "DEMO 活动与资料", "status_code": 200,
                "main_text": "DEMO ONLY. Use Lexmount cloud. Provide completed results and evidence. Deadline 2099-01-01T23:59:00+08:00."}}


class DemoModel:
    calls = 0

    def ask(self, task, context):
        self.calls += 1
        if task.startswith("RULES"):
            return {"title": "DEMO 活动", "deadline": "2099-01-01T23:59:00+08:00",
                    "requirements": [{"text": "Use Lexmount cloud", "quote": "Use Lexmount cloud."}],
                    "unknowns": ["演示没有真实投稿表单"]}
        if task.startswith("IDEAS"):
            return {"ideas": [{"title": "网页资料摘要清单", "description": "整理公开网页并保留来源",
                               "score": 90, "source_urls": ["https://example.com"],
                               "acceptance": "每个页面产生一条带来源的摘要"}]}
        if task.startswith("DESIGN"):
            from .design import fallback_design
            return fallback_design({'selected':context['selected']},context['output'])
        if task.startswith("REVIEW"):
            return {"passed": True, "checks": [{"requirement": "fixture", "passed": True, "reason": "test fixture only"}], "issues": []}
        return {"code": CODE, "explanation": "固定演示程序；不代表模型生成"}
