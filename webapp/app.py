import sys
import os
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, Response, request, stream_with_context
from core import HackingTool, HackingToolsCollection
from hackingtool import all_tools, tool_definitions

app = Flask(__name__)

_registry: dict[str, HackingTool] = {}
_categories: list[dict] = []


def _serialize(tool: HackingTool, tid: str, cat_id: int, cat_name: str, sub_cat: str | None) -> dict:
    return {
        "id": tid,
        "cat_id": cat_id,
        "cat_name": cat_name,
        "sub_cat": sub_cat,
        "title": tool.TITLE,
        "description": tool.DESCRIPTION,
        "project_url": getattr(tool, "PROJECT_URL", ""),
        "tags": getattr(tool, "TAGS", []),
        "supported_os": tool.SUPPORTED_OS,
        "install_commands": tool.INSTALL_COMMANDS,
        "run_commands": tool.RUN_COMMANDS,
        "requires": {
            "root": tool.REQUIRES_ROOT,
            "wifi": tool.REQUIRES_WIFI,
            "go": tool.REQUIRES_GO,
            "ruby": tool.REQUIRES_RUBY,
            "java": tool.REQUIRES_JAVA,
            "docker": tool.REQUIRES_DOCKER,
        },
        "has_install": bool(tool.INSTALL_COMMANDS),
        "has_run": bool(tool.RUN_COMMANDS),
        "installed": tool.is_installed,
    }


def _walk(
    col: HackingToolsCollection,
    cat_id: int,
    cat_name: str,
    out: list,
    counter: list,
    sub_cat: str | None = None,
):
    for item in col.TOOLS:
        if isinstance(item, HackingToolsCollection):
            _walk(item, cat_id, cat_name, out, counter, sub_cat=item.TITLE)
        elif isinstance(item, HackingTool) and not getattr(item, "ARCHIVED", False):
            tid = str(counter[0])
            counter[0] += 1
            _registry[tid] = item
            out.append(_serialize(item, tid, cat_id, cat_name, sub_cat))


def _build():
    counter = [0]
    for i, (_, icon, label) in enumerate(tool_definitions[:20]):
        tools: list[dict] = []
        _walk(all_tools[i], i, label, tools, counter)
        _categories.append({"id": i, "title": label, "icon": icon.strip(), "tools": tools})


_build()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/categories")
def api_categories():
    return jsonify([
        {
            "id": c["id"],
            "title": c["title"],
            "icon": c["icon"],
            "total": len(c["tools"]),
            "installed": sum(1 for t in c["tools"] if t["installed"]),
        }
        for c in _categories
    ])


@app.route("/api/category/<int:cat_id>")
def api_category(cat_id: int):
    if 0 <= cat_id < len(_categories):
        return jsonify(_categories[cat_id]["tools"])
    return jsonify([])


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    results = []
    for cat in _categories:
        for t in cat["tools"]:
            score = 0
            if q in t["title"].lower():
                score += 3
            if q in t["description"].lower():
                score += 1
            if any(q in tag.lower() for tag in t.get("tags", [])):
                score += 2
            if score:
                results.append({**t, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(results[:40])


def _stream(commands: list[str]):
    for cmd in commands:
        yield f"data: {json.dumps({'type': 'cmd', 'text': cmd})}\n\n"
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1", "DEBIAN_FRONTEND": "noninteractive"},
            )
            for line in iter(proc.stdout.readline, ""):
                yield f"data: {json.dumps({'type': 'out', 'text': line.rstrip()})}\n\n"
            proc.wait()
            typ = "ok" if proc.returncode == 0 else "err"
            yield f"data: {json.dumps({'type': typ, 'text': f'[exit {proc.returncode}]'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'err', 'text': str(exc)})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


def _sse(commands: list[str]) -> Response:
    return Response(
        stream_with_context(_stream(commands)),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/install/<tid>")
def api_install(tid: str):
    tool = _registry.get(tid)
    if not tool or not tool.INSTALL_COMMANDS:
        return jsonify({"error": "not found or no install commands"}), 404
    return _sse(tool.INSTALL_COMMANDS)


@app.route("/api/run/<tid>")
def api_run(tid: str):
    tool = _registry.get(tid)
    if not tool or not tool.RUN_COMMANDS:
        return jsonify({"error": "not found or no run commands"}), 404
    return _sse(tool.RUN_COMMANDS)


@app.route("/api/status/<tid>")
def api_status(tid: str):
    tool = _registry.get(tid)
    if not tool:
        return jsonify({"error": "not found"}), 404
    return jsonify({"installed": tool.is_installed})


if __name__ == "__main__":
    print("\n  HackingTool Web UI")
    print("  Open: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
