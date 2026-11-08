"""Loopback dashboard API, optionally behind an authenticated HTTPS proxy."""
import json
import fcntl
import os
import re
import secrets
import shutil
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .common import WorkflowError, now, public_url, read_json, write_json
from .workflow import STAGES, Workflow

WEB = Path(__file__).parent / "web"
ARTIFACTS = {"rules.json", "ideas.json", "spec.json", "main.py", "tests.json", "output.json",
             "submission.md", "submission.json", "manifest.json", "submission.zip", "submission-state.json", "release-state.json", "review.json", "review-errors.json", "visual-review.json", "visual-history.json", "visual-theme.json", "visual-evidence.zip", "citations.json", "citation-errors.json", "quality.json", "index.html", "test-history.json", "model-events.json", "design.json", "design-error.json", "reader.json", "reader-review.json", "reader-history.json", "reader-review-errors.json"}


def configuration():
    return {"lexmount": bool((os.getenv("LEXMOUNT_API_KEY") and os.getenv("LEXMOUNT_PROJECT_ID")) or
                             (os.getenv("LEXMOUNT_FETCH_CLI") and Path(os.environ["LEXMOUNT_FETCH_CLI"]).is_file())),
            "model": bool(os.getenv("MODEL_API_KEY") and os.getenv("MODEL_NAME")),
            "docker": bool(shutil.which("docker"))}


class Dashboard:
    def __init__(self, root, workflow=Workflow):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.workflow = workflow
        self.public_origin = os.getenv("AUTOLEX_PUBLIC_ORIGIN", "")
        if self.public_origin:
            parsed = urlsplit(self.public_origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                    or self.public_origin != "https://" + parsed.netloc):
                raise WorkflowError("AUTOLEX_PUBLIC_ORIGIN 必须是完整的 HTTPS 来源地址，不含路径")
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.active = set()
        self.errors = {}
        self.release_errors = {}

    def directory(self, run_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,90}", run_id):
            raise WorkflowError("无效的任务 ID")
        path = self.root / run_id
        if path.is_symlink() or path.resolve().parent != self.root:
            raise WorkflowError("任务目录不可访问")
        return path

    def artifact(self, run_id, filename):
        if filename not in ARTIFACTS:
            raise WorkflowError("文件不可访问")
        path = self.directory(run_id) / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise WorkflowError("文件不存在或过大")
        return path

    def detail(self, run_id, full=True):
        directory = self.directory(run_id)
        if not directory.is_dir():
            raise WorkflowError("任务不存在")
        state_file = directory / "state.json"
        if state_file.is_symlink() or (state_file.is_file() and state_file.stat().st_size > 1_000_000):
            raise WorkflowError("任务状态不可读取")
        state = read_json(state_file) if state_file.is_file() else {
            "status": "queued", "completed": [], "demo": True}
        with self.lock:
            active = run_id in self.active
            error = self.errors.get(run_id)
            release_error = self.release_errors.get(run_id)
        lockfile = directory / ".lock"
        if not active and lockfile.is_file() and not lockfile.is_symlink():
            with lockfile.open("r") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(lock, fcntl.LOCK_UN)
                except BlockingIOError:
                    active = True
        state = {**state, "id": run_id, "active": active}
        # A killed process may leave running on disk; don't pretend it is still working.
        if not active and state.get("status") in {"running", "queued"}:
            state["status"] = "interrupted"
        if error:
            state.update(status="blocked", error=error)
        state.pop("hashes", None)
        data = {"state": state, "artifacts": sorted(name for name in ARTIFACTS
                 if (directory / name).is_file() and not (directory / name).is_symlink())}
        spec_path = directory / "spec.json"
        spec = read_json(spec_path) if spec_path.is_file() and not spec_path.is_symlink() and spec_path.stat().st_size < 1_000_000 else {}
        data["summary"] = {"title": spec.get("selected", {}).get("title", run_id),
                           "parent": state.get("visual_parent") or (spec.get("revision") or {}).get("parent")}
        data["release_configured"] = bool(os.getenv("AUTOLEX_RELEASE_PROFILE") and Path(os.environ["AUTOLEX_RELEASE_PROFILE"]).is_file())
        data['release_error'] = release_error
        if full:
            for name, key in (("rules.json", "rules"), ("ideas.json", "ideas"), ("spec.json", "spec"),
                              ("tests.json", "tests"), ("test-history.json", "test_history"), ("model-events.json", "model_events"), ("review.json", "review"), ("citations.json", "citations"), ("visual-review.json", "visual"), ("quality.json", "quality"), ("output.json", "output"), ("submission-state.json", "submission"), ("release-state.json", "release")):
                path = directory / name
                if path.is_file() and not path.is_symlink() and path.stat().st_size < 1_000_000:
                    data[key] = read_json(path)
            for name, key in (("main.py", "code"), ("submission.md", "report")):
                path = directory / name
                if path.is_file() and not path.is_symlink() and path.stat().st_size < 200_000:
                    data[key] = path.read_text()
            items = data.get("output", {}).get("items", [])
            histories = [*data.get("test_history", []), data.get("tests", {})]
            data["summary"].update(sources=len(items), points=sum(len(item.get("points", [])) for item in items),
                                   conclusions=len(data.get("output", {}).get("conclusions", [])),
                                   attempts=sum(len(report.get("attempts", [])) for report in histories),
                                   next_step=("打开作品预览，沿引用核对结论。" if state.get("status") == "ready" else
                                              "查看测试记录中的最近一次失败，再继续或按反馈创建新版本。" if state.get("status") == "blocked" else
                                              "正在执行，进展会自动更新。" if active else "可继续完成剩余阶段。"))
        return data

    def listing(self):
        records = []
        for directory in self.root.iterdir():
            if directory.is_dir() and not directory.is_symlink():
                if not (directory / "state.json").is_file():
                    continue
                try:
                    records.append(self.detail(directory.name, full=False))
                except (WorkflowError, ValueError, OSError):
                    continue
        return sorted(records, key=lambda item: item["state"].get("created_at", item["state"]["id"]), reverse=True)

    def launch(self, payload, run_id=None):
        if not isinstance(payload, dict):
            raise WorkflowError("请求必须是 JSON 对象")
        until = payload.get("until", "package")
        repairs = payload.get("repairs", 3)
        auto_release = payload.get('auto_release', False)
        if type(auto_release) is not bool:
            raise WorkflowError('自动投稿选项必须是布尔值')
        if until not in STAGES or type(repairs) is not int or not 0 <= repairs <= 3:
            raise WorkflowError("无效的阶段或修复次数")
        if run_id:
            previous = self.detail(run_id)["state"]
            url, demo = previous["url"], previous["demo"]
            brief = previous.get("brief", "")
            auto_release = previous.get('auto_release', False)
            if previous.get("status") == "ready":
                raise WorkflowError("任务已完成，请创建新任务")
        else:
            mode = payload.get("mode", "demo")
            if mode not in {"demo", "live"}:
                raise WorkflowError("无效的运行模式")
            demo = mode == "demo"
            brief = payload.get("brief", "")
            if not isinstance(brief, str) or len(brief) > 6000:
                raise WorkflowError("任务方向最多 6000 字符")
            url = public_url(payload.get("url", ""))
            run_id = "web-" + datetime.now().strftime("%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        if not demo and not all(configuration().values()):
            raise WorkflowError("真实运行需要先在服务端配置 Lexmount、模型和 Docker")
        directory = self.directory(run_id)
        revision = None
        if not (directory / "state.json").exists() and payload.get("revision_of"):
            parent = self.detail(payload["revision_of"])
            if parent["state"].get("active") or "build" not in parent["state"].get("completed", []):
                raise WorkflowError("原任务需先完成构建并停止运行，才能创建新版本")
            feedback = payload.get("feedback", "")
            if not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 6000:
                raise WorkflowError("请填写 1–6000 字符的修改反馈")
            url, demo, brief = parent["state"]["url"], parent["state"]["demo"], parent["state"].get("brief", "")
            if not demo and not all(configuration().values()):
                raise WorkflowError("真实运行需要先在服务端配置 Lexmount、模型和 Docker")
            revision = {"parent": parent["state"]["id"], "selected": parent["spec"]["selected"],
                        "previous_code": parent["code"], "feedback": feedback}
        if auto_release and (demo or until!='package' or not os.getenv('AUTOLEX_RELEASE_PROFILE')):
            raise WorkflowError('自动投稿需要真实完整流程和服务端投稿配置')
        with self.lock:
            if self.active:
                raise WorkflowError("已有任务在运行，完成后再启动下一个任务")
            self.active.add(run_id)
            self.errors.pop(run_id, None)
        try:
            directory.mkdir(exist_ok=True)
            if not (directory / "state.json").exists():
                write_json(directory / "state.json", {"url": url, "demo": demo, "created_at": now(),
                           "completed": [], "hashes": {}, "model_calls": 0, "status": "queued", "brief": brief, "revision": revision, "auto_release": auto_release})
            thread = threading.Thread(target=self._work, args=(run_id, url, demo, repairs, until, auto_release), daemon=True)
            thread.start()
        except Exception:
            with self.lock:
                self.active.discard(run_id)
            raise
        return {"id": run_id}

    def _work(self, run_id, url, demo, repairs, until, auto_release=False):
        publishing=False
        try:
            self.workflow(self.directory(run_id), url, demo=demo, repairs=repairs).run(until)
            if auto_release:
                publishing=True
                from .release import release
                release(self.directory(run_id),read_json(os.environ['AUTOLEX_RELEASE_PROFILE']),send=True)
        except Exception as exc:
            with self.lock:
                (self.release_errors if publishing else self.errors)[run_id] = str(exc) if isinstance(exc, WorkflowError) else type(exc).__name__
        finally:
            with self.lock:
                self.active.discard(run_id)

    def launch_release(self, run_id):
        from .release import prepare_release
        detail=self.detail(run_id)
        if detail['state'].get('active'):
            raise WorkflowError('当前任务仍在运行')
        profile_path=os.getenv('AUTOLEX_RELEASE_PROFILE')
        if not profile_path:
            raise WorkflowError('请先在服务端配置 AUTOLEX_RELEASE_PROFILE')
        profile=read_json(profile_path)
        prepare_release(self.directory(run_id),profile)
        with self.lock:
            if self.active:raise WorkflowError('已有任务在运行')
            self.active.add(run_id);self.release_errors.pop(run_id,None)
        def work():
            try:
                from .release import release
                release(self.directory(run_id),profile,send=True)
            except Exception as exc:
                with self.lock:self.release_errors[run_id]=str(exc) if isinstance(exc,WorkflowError) else type(exc).__name__
            finally:
                with self.lock:self.active.discard(run_id)
        try:threading.Thread(target=work,daemon=True).start()
        except Exception:
            with self.lock:self.active.discard(run_id)
            raise
        return {'id':run_id,'action':'release'}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def local_request(self, mutation=False):
            host = self.headers.get("Host", "")
            port = self.server.server_port
            origins = {f"localhost:{port}": f"http://localhost:{port}",
                       f"127.0.0.1:{port}": f"http://127.0.0.1:{port}"}
            if app.public_origin:
                origins[urlsplit(app.public_origin).netloc] = app.public_origin
            if host not in origins:
                return False
            origin = self.headers.get("Origin")
            if origin and origin != origins[host]:
                return False
            return not mutation or secrets.compare_digest(self.headers.get("X-Autolex-Token", ""), app.token)

        def send(self, status, data, content_type="application/json; charset=utf-8", filename=None, policy=None):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", policy or "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.local_request():
                return self.send(403, {"error": "访问地址或来源未获允许"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    return self.send(200, {"token": app.token, "configuration": configuration(), "version": "0.1.0"})
                if path == "/api/runs":
                    return self.send(200, {"runs": app.listing()})
                pieces = path.strip("/").split("/")
                if pieces[:2] == ["api", "runs"] and len(pieces) == 3:
                    return self.send(200, app.detail(pieces[2]))
                if pieces[:2] == ["api", "runs"] and len(pieces) == 4 and pieces[3] == "preview":
                    file = app.artifact(pieces[2], "index.html")
                    return self.send(200, file.read_bytes(), "text/html; charset=utf-8",
                                     policy="sandbox allow-popups allow-popups-to-escape-sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
                if pieces[:2] == ["api", "runs"] and len(pieces) == 5 and pieces[3] == "files":
                    file = app.artifact(pieces[2], pieces[4])
                    return self.send(200, file.read_bytes(), "application/octet-stream", file.name)
                static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                          "/styles.css": ("styles.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if path in static:
                    name, mime = static[path]
                    return self.send(200, (WEB / name).read_bytes(), mime + "; charset=utf-8")
                return self.send(404, {"error": "页面不存在"})
            except (WorkflowError, OSError, ValueError, KeyError):
                return self.send(404, {"error": "任务或文件不可读取"})

        def do_POST(self):
            if not self.local_request(mutation=True):
                return self.send(403, {"error": "请求校验失败，请刷新页面"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.send(400, {"error": "需要有效的 JSON 请求"})
                payload = json.loads(self.rfile.read(length))
                pieces = urlsplit(self.path).path.strip("/").split("/")
                if pieces == ["api", "runs"]:
                    return self.send(202, app.launch(payload))
                if pieces[:2] == ["api", "runs"] and len(pieces) == 4 and pieces[3] == "resume":
                    return self.send(202, app.launch(payload, pieces[2]))
                if pieces[:2] == ["api", "runs"] and len(pieces) == 4 and pieces[3] == "release":
                    return self.send(202, app.launch_release(pieces[2]))
                return self.send(404, {"error": "接口不存在"})
            except WorkflowError as exc:
                return self.send(400, {"error": str(exc)})
            except (ValueError, TypeError, KeyError, OSError):
                return self.send(400, {"error": "无效的请求数据"})
    return Handler


def serve(root="runs", port=8765):
    if not 1024 <= port <= 65535:
        raise WorkflowError("端口应在 1024–65535 之间")
    app = Dashboard(root)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(app))
    except PermissionError:
        raise WorkflowError("当前环境不允许监听本机端口，请在本机终端运行 python -m autolex serve") from None
    print(f"Auto Lexmount 控制台：http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
