"""Evidence perturbation checks. These are reproducibility tests, not official scores."""
import ast
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from .common import WorkflowError, read_json, write_json
from .runner import execute, validate_output


def count_bounds(acceptance, noun):
    # Only parse explicit numeric requirements; prose still goes through semantic review.
    tail = r"\s*条[^，。；、\n\d]{0,15}" + noun
    ranged = re.search(r"(\d+)\s*[-–—至到]\s*(\d+)" + tail, acceptance)
    if ranged:
        return tuple(map(int, ranged.groups()))
    counted = re.search(r"(至少|不少于|最少|至多|不超过|最多)?\s*(\d+)" + tail, acceptance)
    if counted:
        operator, number = counted.groups()
        number = int(number)
        if operator in {"至少", "不少于", "最少"}:
            return number, None
        if operator in {"至多", "不超过", "最多"}:
            return 0, number
        return number, number
    return None


def acceptance_metrics(output, acceptance, brief=""):
    points = [p for item in output.get("items", []) for p in item.get("points", [])]
    conclusions = output.get("conclusions", [])
    text = " ".join([str(item.get("summary", "")) for item in output.get("items", [])] +
                    [str(p.get("summary", "")) for p in points] + [str(c.get("text", "")) for c in conclusions])
    metrics = {"points_total": len(points), "conclusions_total": len(conclusions),
               "chinese_characters_in_summaries_and_conclusions": len(re.findall(r"[\u4e00-\u9fff]", text))}
    failures = []
    for noun, label, actual in (("要点", "points TOTAL", len(points)), ("结论", "conclusions", len(conclusions))):
        bounds = count_bounds(brief, noun) or count_bounds(acceptance, noun)
        if bounds:
            low, high = bounds
            if actual < low or high is not None and actual > high:
                requirement = f"exactly {low}" if low == high else f"{low}-{high if high is not None else 'unbounded'}"
                failures.append(f"Acceptance requires {requirement} {label}, but output has {actual}")
    return metrics, failures


def normalized(output):
    data = copy.deepcopy(output)
    data["items"] = sorted(data.get("items", []), key=lambda item: item["url"])
    for item in data["items"]:
        for point in item.get("points", []):
            point["quote"] = " ".join(point["quote"].split())
    return data


def evidence_refusal(result, work):
    """A runtime crash or killed container is not a successful validation decision."""
    if (not 0 < result["returncode"] < 126 or result.get("timeout") or
            (work / "output.json").exists()):
        return False
    diagnostic = result.get("log", "").strip().splitlines()
    last = diagnostic[-1] if diagnostic else ""
    if re.search(r"(?:Name|Type|Index|Key|Attribute|Syntax|ZeroDivision|Memory)Error:", last):
        return False
    return bool(re.search(r"EVIDENCE_ERROR|(?:missing|empty|no |cannot|not found|insufficient|invalid).*(?:evidence|source|page|quote|main_text)|(?:evidence|source|page|quote|main_text).*(?:missing|empty|not found|invalid)", last, re.I))


def robustness(code, evidence, expected, directory, executor=execute):
    directory = Path(directory)
    checks = []
    variants = [("repeat", copy.deepcopy(evidence)), ("reverse_pages", copy.deepcopy(evidence)),
                ("missing_page", copy.deepcopy(evidence)), ("empty_evidence", copy.deepcopy(evidence)),
                ("irrelevant_evidence", copy.deepcopy(evidence))]
    variants[1][1]["pages"].reverse()
    variants[2][1]["pages"][0]["result"]["main_text"] = ""
    for page in variants[3][1]["pages"]:
        page["result"]["main_text"] = ""
    for page in variants[4][1]["pages"]:
        page["result"]["main_text"] = "NO_RELEVANT_SOURCE_EVIDENCE: this replacement contains none of the original facts."
    whitespace = copy.deepcopy(evidence)
    for page in whitespace["pages"]:
        page["result"]["main_text"] = re.sub(r"\s+", "\n \t", page["result"]["main_text"])
    variants.append(("equivalent_whitespace", whitespace))
    for index in range(len(evidence["pages"])):
        missing = copy.deepcopy(evidence)
        missing["pages"].pop(index)
        variants.append((f"missing_source_{index + 1}", missing))
        if index:  # First empty page is already covered by missing_page.
            empty = copy.deepcopy(evidence)
            empty["pages"][index]["result"]["main_text"] = ""
            variants.append((f"empty_source_{index + 1}", empty))
    duplicate = copy.deepcopy(evidence)
    duplicate["pages"].append(copy.deepcopy(duplicate["pages"][0]))
    variants.append(("duplicate_source", duplicate))
    for name, data in variants:
        work = directory / (name + "-" + uuid.uuid4().hex[:8]) / "project"
        work.mkdir(parents=True)
        (work / "main.py").write_text(code, encoding="utf-8")
        write_json(work / "input.json", data)
        result = executor(work)
        output = None
        failures = validate_output(work, data)
        if not failures:
            output = read_json(work / "output.json")
        if name in {"repeat", "reverse_pages", "equivalent_whitespace"}:
            passed = result["returncode"] == 0 and not failures and normalized(output) == normalized(expected)
            reason = "Same evidence must produce the same facts and summaries, including page reordering or whitespace-only source changes. Normalize whitespace before matching quotes."
        else:
            passed = evidence_refusal(result, work)
            reason = "Missing, duplicate, empty or irrelevant required sources must be explicitly refused before writing output.json. Exit with EVIDENCE_ERROR: reason; an unexpected crash is not a valid refusal."
        checks.append({"name": name, "passed": bool(passed), "requirement": reason,
                       "failures": failures if not passed else [], "returncode": result["returncode"],
                       "log": result.get("log", ""), "artifact": str(work.relative_to(directory))})
    return {"version": 3, "passed": all(c["passed"] for c in checks), "checks": checks,
            "scope": "Deterministic evidence perturbations; not a semantic or visual judgment"}


def inspect_code(code):
    tree = ast.parse(code)
    imports = sorted({name for node in ast.walk(tree) for name in
                      ([alias.name for alias in node.names] if isinstance(node, ast.Import) else
                       [node.module or ""] if isinstance(node, ast.ImportFrom) else [])})
    return {"lines": len(code.splitlines()), "imports": imports,
            "functions": [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))],
            "sha256": hashlib.sha256(code.encode()).hexdigest(),
            "note": "Static inventory only; source-specific constants are allowed for snapshot tasks."}


def audit_run(root, output, executor=execute):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise WorkflowError("Audit output must be outside the original run")
    state = read_json(root / "state.json")
    for name, digest in state.get("hashes", {}).items():
        path = root / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise WorkflowError("Audit refused changed artifact: " + name)
    if state.get("demo"):
        raise WorkflowError("Docker quality audit requires a live run")
    output.mkdir(parents=True, exist_ok=True)
    candidate = root
    if not (root / "output.json").exists():
        candidates = list(root.glob("attempts/*/project/output.json"))
        if not candidates:
            raise WorkflowError("No executable output available for audit")
        candidate = max(candidates, key=lambda p: p.stat().st_mtime_ns).parent
    code = (candidate / "main.py").read_text()
    report = {"run": root.name, "workflow_status": state.get("status"), "candidate": str(candidate.relative_to(root)), "code": inspect_code(code),
              "robustness": robustness(code, read_json(root / "input.json"), read_json(candidate / "output.json"), output, executor),
              "files": [{"name": p.name, "bytes": p.stat().st_size} for p in sorted(root.iterdir()) if p.is_file() and not p.name.startswith(".")],
              "preview_available": (root / "index.html").is_file(),
              "visual_review": "pending: inspect real screenshots separately"}
    write_json(output / "audit.json", report)
    return report


def quotation_hints(code, evidence):
    """Offer counted literal quotes and adjacent source context for focused repairs.

    These are suggestions, never automatic substitutions in generated code.
    The model must preserve the meaning and every regular validator still runs.
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError):
        return []
    sources = [(page['url'], ' '.join(page['result']['main_text'].split())) for page in evidence.get('pages', [])]
    hints = []; seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = ' '.join(node.value.split()); words = value.split()
        if not 4 <= len(words) <= 120 or value in seen:
            continue
        for url, source in sources:
            if value in source:
                hints.append({'url': url, 'original_quote': value, 'word_count': len(words),
                              'source_context': source[max(0, source.index(value)-160):source.index(value)+len(value)+160],
                              'prefix_25_words': ' '.join(words[:25]), 'suffix_25_words': ' '.join(words[-25:]),
                              'instruction': 'These are counted contiguous source excerpts, not guaranteed semantic replacements. Choose an appropriate excerpt and narrow the summary, or select a different source passage. Do not drop required topics.'})
                seen.add(value)
                break
        if len(hints) >= 8:
            break
    return hints
