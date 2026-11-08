import argparse
import json
import os
import shutil
from pathlib import Path

from .common import WorkflowError, read_json
from .submission import submit
from .workflow import STAGES, Workflow

URL = "https://browser.lexmount.cn/events/real-task-challenge"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Auto Lexmount · 快乐参赛流水线")
    parser.add_argument("--env-file", help="Load explicit local configuration without shell evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "run"):
        command = commands.add_parser(name)
        command.add_argument("--url", default=URL)
        command.add_argument("--out", default="runs/" + name)
        command.add_argument("--until", choices=STAGES, default="package")
        command.add_argument("--repairs", type=int, default=3)
        command.add_argument("--brief", help="Task direction and acceptance constraints")
        command.add_argument("--revise-from", help="Previous completed run; retain its selected task")
        command.add_argument("--feedback", help="UTF-8 feedback file for this new revision")
        if name == "run":
            command.add_argument("--submit-config", help="Continue into the configured website form after packaging")
            command.add_argument("--release-profile", help="Publish and submit this generated work through Yours and the challenge form")
            command.add_argument("--visual-review", action="store_true", help="Review screenshots and repair presentation before packaging")
            command.add_argument("--send", action="store_true", help="Submit the form after packaging")
    commands.add_parser("doctor")
    configure = commands.add_parser("configure-deepseek", help="Store a key through hidden terminal input")
    configure.add_argument("--output", default=".env")
    commands.add_parser("check-model", help="Make one small real model request")
    web = commands.add_parser("serve", help="Launch the local web dashboard")
    web.add_argument("--runs", default="runs")
    web.add_argument("--port", type=int, default=8765)
    status = commands.add_parser("status")
    status.add_argument("run")
    audit = commands.add_parser("audit", help="Inspect code/files and run evidence perturbation tests")
    audit.add_argument("run")
    audit.add_argument("--out", required=True, help="Separate audit directory; original artifacts stay immutable")
    submission = commands.add_parser("submit")
    submission.add_argument("run")
    submission.add_argument("--config", required=True)
    submission.add_argument("--send", action="store_true", help="Actually click submit; omitted means form preview")
    publication = commands.add_parser("release", help="Publish and submit a generated work, with its own URL and receipt")
    publication.add_argument("run")
    publication.add_argument("--profile", required=True)
    publication.add_argument("--send", action="store_true", help="Actually publish and submit; omitted prepares local materials only")
    recovery = commands.add_parser("recover-release", help="Verify an existing work URL after an uncertain publication; never upload again")
    recovery.add_argument("run")
    recovery.add_argument("--profile", required=True)
    recovery.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    try:
        if args.env_file:
            from .config import load_environment
            load_environment(args.env_file)
        if args.command == "configure-deepseek":
            from .config import configure_deepseek
            print(json.dumps(configure_deepseek(args.output), ensure_ascii=False))
            return 0
        if args.command == "check-model":
            from .clients import Model
            response = Model(max_calls=1).ask('Return JSON exactly like {"ok": true}.', {"task": "connectivity check"})
            if response != {"ok": True}:
                raise WorkflowError("Model check returned unexpected content")
            print(json.dumps({"ok": True, "model": os.getenv("MODEL_NAME")}))
            return 0
        if args.command == "serve":
            from .server import serve
            serve(args.runs, args.port)
            return 0
        if args.command == "doctor":
            checks = {"lexmount_credentials": bool(os.getenv("LEXMOUNT_API_KEY") and os.getenv("LEXMOUNT_PROJECT_ID")),
                      "lexmount_cli": bool(os.getenv("LEXMOUNT_FETCH_CLI") and Path(os.environ["LEXMOUNT_FETCH_CLI"]).is_file()),
                      "model_configured": bool(os.getenv("MODEL_API_KEY") and os.getenv("MODEL_NAME")),
                      "docker_installed": bool(shutil.which("docker")),
                      "note": "Configuration check only; does not verify network, Docker daemon or API authentication"}
            print(json.dumps(checks, ensure_ascii=False, indent=2))
            return 0 if (checks["lexmount_credentials"] or checks["lexmount_cli"]) and checks["model_configured"] and checks["docker_installed"] else 2
        if args.command == "status":
            result = read_json(Path(args.run) / "state.json")
        elif args.command == "audit":
            from .quality import audit_run
            result = audit_run(args.run, args.out)
        elif args.command == "submit":
            result = submit(args.run, read_json(args.config), send=args.send)
        elif args.command == "release":
            from .release import release
            result = release(args.run, read_json(args.profile), send=args.send)
        elif args.command == "recover-release":
            from .release import recover_publication
            result = recover_publication(args.run, read_json(args.profile), args.url)
        else:
            if args.command == "run" and args.send and not (args.submit_config or args.release_profile):
                raise WorkflowError("--send requires --submit-config or --release-profile")
            if args.command == "run" and args.submit_config and args.release_profile:
                raise WorkflowError("Choose one submission adapter")
            if args.command == "run" and (args.submit_config or args.release_profile) and args.until != "package":
                raise WorkflowError("Submission requires --until package")
            revision = None
            if args.revise_from:
                if not args.feedback:
                    raise WorkflowError("--revise-from requires --feedback")
                previous = Path(args.revise_from).resolve()
                if previous == Path(args.out).resolve():
                    raise WorkflowError("Revision requires a new output directory")
                state = read_json(previous / "state.json")
                if "build" not in state.get("completed", []) or state.get("demo") != (args.command == "demo"):
                    raise WorkflowError("Revision requires a built run in the same mode")
                revision = {"parent": previous.name, "selected": read_json(previous / "spec.json")["selected"],
                            "previous_code": (previous / "main.py").read_text(encoding="utf-8"),
                            "feedback": Path(args.feedback).read_text(encoding="utf-8")[:12000]}
            elif args.feedback:
                raise WorkflowError("--feedback requires --revise-from")
            if args.command == "run" and args.visual_review:
                os.environ["AUTOLEX_VISUAL_REVIEW"] = "true"
            result = Workflow(args.out, args.url, demo=args.command == "demo", repairs=args.repairs,
                              brief=args.brief, revision=revision).run(args.until)
            if args.command == "run" and args.submit_config:
                result = {"workflow": result, "submission": submit(args.out, read_json(args.submit_config), send=args.send)}
            if args.command == "run" and args.release_profile:
                from .release import release
                result = {"workflow": result, "release": release(args.out, read_json(args.release_profile), send=args.send)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError) as exc:
        # SDK exception strings can contain connection credentials. Report generic names for those.
        message = str(exc) if isinstance(exc, WorkflowError) else type(exc).__name__
        print(json.dumps({"error": message}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
