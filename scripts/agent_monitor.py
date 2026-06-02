#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ACTIVITIES = {"IDLE", "BUSY", "NEEDS_HUMAN"}
ACTIVE_STATUSES = {"STARTING", "RUNNING", "PAUSED"}
ALL_STATUSES = ACTIVE_STATUSES | {"COMPLETED", "FAILED", "STOPPED", "WAITING", "STALLED"}
CODEX_HOOK_EVENTS = {
    "Notification",
    "PermissionRequest",
    "PostToolUse",
    "PreToolUse",
    "SessionEnd",
    "SessionStart",
    "Stop",
    "UserPromptSubmit",
}

STATUS_PRIORITY = {
    "FAILED": 100,
    "NEEDS_HUMAN": 90,
    "STALLED": 80,
    "BUSY": 70,
    "IDLE": 50,
    "NONE": 0,
}

STATUS_COLORS = {
    "IDLE": "colour22",
    "BUSY": "yellow",
    "NEEDS_HUMAN": "red",
    "FAILED": "red",
    "STALLED": "magenta",
    "NONE": "colour244",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def monitor_home() -> Path:
    return Path(os.environ.get("AGENT_MONITOR_HOME") or "~/.agent-monitor").expanduser()


def state_dir() -> Path:
    return monitor_home() / "state"


def agent_state_path() -> Path:
    return monitor_home() / "codex-state.json"


def agent_state_lock_path() -> Path:
    return monitor_home() / "codex-state.lock"


def ensure_dirs() -> None:
    monitor_home().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)


def validate_agent_id(agent_id: str) -> None:
    if "/" in agent_id or "\x00" in agent_id or agent_id in {"", ".", ".."}:
        raise SystemExit(f"invalid agent id: {agent_id!r}")


def empty_agent_state() -> dict[str, Any]:
    return {"version": 1, "agents": {}}


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_agent_state_unlocked() -> dict[str, Any]:
    data = read_json(agent_state_path())
    if not data:
        return empty_agent_state()
    if not isinstance(data.get("agents"), dict):
        data["agents"] = {}
    data.setdefault("version", 1)
    return data


def write_agent_state_unlocked(data: dict[str, Any]) -> None:
    ensure_dirs()
    data.setdefault("version", 1)
    if not isinstance(data.get("agents"), dict):
        data["agents"] = {}
    path = agent_state_path()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


@contextmanager
def locked_agent_state() -> Iterator[dict[str, Any]]:
    ensure_dirs()
    with agent_state_lock_path().open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = read_agent_state_unlocked()
            yield data
            write_agent_state_unlocked(data)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def bool_arg(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def normalize_activity(value: str | None) -> str | None:
    if value is None:
        return None
    activity = value.upper().replace("-", "_")
    if activity == "WAITING":
        activity = "NEEDS_HUMAN"
    if activity not in ACTIVITIES:
        raise SystemExit(f"unknown activity: {value}")
    return activity


def default_activity(status: str, needs_human: bool) -> str:
    if needs_human or status == "WAITING":
        return "NEEDS_HUMAN"
    if status in {"RUNNING", "STARTING"}:
        return "BUSY"
    return "IDLE"


def stalled_timeout() -> int:
    try:
        return max(1, int(os.environ.get("AGENT_MONITOR_STALL_TIMEOUT", "600")))
    except ValueError:
        return 600


def effective_status(agent: dict[str, Any]) -> str:
    status = str(agent.get("status") or "STOPPED").upper()
    activity = normalize_activity(str(agent.get("activity"))) if agent.get("activity") else None
    if status in ACTIVE_STATUSES and activity == "BUSY":
        last_update = parse_time(agent.get("last_update"))
        if last_update and (now_utc() - last_update).total_seconds() > stalled_timeout():
            return "STALLED"
    return status


def upsert_agent(args: argparse.Namespace, *, register: bool) -> None:
    validate_agent_id(args.agent)
    status = args.status.upper()
    if status not in ALL_STATUSES:
        raise SystemExit(f"unknown status: {args.status}")

    timestamp = iso_now()
    requested_activity = normalize_activity(getattr(args, "activity", None))

    with locked_agent_state() as state:
        agents = state.setdefault("agents", {})
        existing = agents.get(args.agent, {})
        if not isinstance(existing, dict):
            existing = {}

        needs_human = (
            bool(args.needs_human)
            if args.needs_human is not None
            else bool(existing.get("needs_human", False))
        )
        if status != "WAITING" and args.needs_human is None:
            needs_human = False

        data = {
            "agent_id": args.agent,
            "status": status,
            "activity": requested_activity or default_activity(status, needs_human),
            "task": args.task if args.task is not None else existing.get("task", ""),
            "window": args.window if args.window is not None else existing.get("window", ""),
            "window_id": args.window_id if args.window_id is not None else existing.get("window_id", ""),
            "session": args.session if args.session is not None else existing.get("session", ""),
            "pane": args.pane if args.pane is not None else existing.get("pane", ""),
            "started_at": timestamp if register else existing.get("started_at", timestamp),
            "last_update": timestamp,
            "needs_human": needs_human,
        }
        if args.message is not None:
            data["message"] = args.message
        elif "message" in existing:
            data["message"] = existing["message"]
        agents[args.agent] = data


def delete_agent(args: argparse.Namespace) -> None:
    validate_agent_id(args.agent)
    with locked_agent_state() as state:
        state.setdefault("agents", {}).pop(args.agent, None)


def prune_agents(args: argparse.Namespace) -> None:
    prune_statuses = {"COMPLETED", "STOPPED"}
    if args.failed:
        prune_statuses.add("FAILED")
    with locked_agent_state() as state:
        agents = state.setdefault("agents", {})
        for agent_id, agent in list(agents.items()):
            if not isinstance(agent, dict) or str(agent.get("status") or "").upper() in prune_statuses:
                agents.pop(agent_id, None)


def codex_hook_activity(event: str) -> tuple[str, str, bool] | None:
    if event in {"PermissionRequest", "Notification"}:
        return ("RUNNING", "NEEDS_HUMAN", True)
    if event in {"PreToolUse", "PostToolUse", "UserPromptSubmit"}:
        return ("RUNNING", "BUSY", False)
    if event in {"SessionStart", "Stop"}:
        return ("RUNNING", "IDLE", False)
    if event == "SessionEnd":
        return ("STOPPED", "IDLE", False)
    return None


def codex_hook(args: argparse.Namespace) -> None:
    agent_id = args.agent or os.environ.get("AGENT_ID") or os.environ.get("AGENT_MONITOR_AGENT_ID")
    if not agent_id:
        return
    try:
        validate_agent_id(agent_id)
    except SystemExit:
        return

    event = args.event.strip()
    if event not in CODEX_HOOK_EVENTS:
        return

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    next_state = codex_hook_activity(event)
    if next_state is None:
        return

    status, activity, needs_human = next_state
    timestamp = iso_now()
    message = str(payload.get("message") or payload.get("title") or event) if isinstance(payload, dict) else event

    with locked_agent_state() as state:
        agents = state.setdefault("agents", {})
        existing = agents.get(agent_id, {})
        if not isinstance(existing, dict):
            existing = {}

        existing.update(
            {
                "agent_id": agent_id,
                "status": status,
                "activity": activity,
                "last_update": timestamp,
                "needs_human": needs_human,
                "last_hook_event": event,
                "message": message,
            }
        )
        existing.setdefault("task", "codex")
        existing.setdefault("started_at", timestamp)
        agents[agent_id] = existing


def capture_pane_text(pane: str) -> str:
    if not pane or not shutil.which("tmux"):
        return ""
    result = subprocess.run(
        ["tmux", "capture-pane", "-pt", pane, "-S", "-80"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def pane_current_path(pane: str) -> Path | None:
    if not pane or not shutil.which("tmux"):
        return None
    result = subprocess.run(
        ["tmux", "display-message", "-p", "-t", pane, "#{pane_current_path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    current_path = result.stdout.strip() if result.returncode == 0 else ""
    return Path(current_path).expanduser() if current_path else None


def idea_file_count_for_pane(pane: str) -> int:
    current_path = pane_current_path(pane)
    if current_path is None:
        return 0

    idea_path = current_path / "idea"
    if not idea_path.is_dir():
        return 0

    try:
        return sum(1 for path in idea_path.rglob("*") if path.is_file())
    except OSError:
        return 0


def last_nonempty_lines(text: str, count: int = 14) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()][-count:]


def pane_state_path(pane: str) -> Path:
    safe = pane.replace("%", "pane-").replace("/", "_")
    return state_dir() / f"{safe}.json"


def pane_is_changing(agent: dict[str, Any], pane_text: str) -> bool:
    pane = str(agent.get("pane", ""))
    if not pane:
        return False

    ensure_dirs()
    path = pane_state_path(pane)
    digest = hashlib.sha256(pane_text.encode("utf-8", errors="ignore")).hexdigest()
    timestamp = now_utc().timestamp()
    previous = read_json(path)

    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump({"agent_id": agent.get("agent_id", ""), "hash": digest, "updated_at": timestamp}, handle)
        handle.write("\n")
    tmp.replace(path)

    previous_hash = previous.get("hash")
    previous_time = previous.get("updated_at")
    return bool(previous_hash and isinstance(previous_time, (int, float)) and previous_hash != digest and timestamp - previous_time <= 5)


def infer_codex_activity(agent: dict[str, Any]) -> str | None:
    if "codex" not in str(agent.get("task", "")).lower():
        return normalize_activity(str(agent.get("activity"))) if agent.get("activity") else None

    pane_text = capture_pane_text(str(agent.get("pane", "")))
    if not pane_text:
        return normalize_activity(str(agent.get("activity"))) if agent.get("activity") else None
    pane_changing = pane_is_changing(agent, pane_text)
    agent["_pane_changing"] = pane_changing
    if pane_changing:
        return "BUSY"

    lines = last_nonempty_lines(pane_text)
    lowered = [line.lower() for line in lines]
    prompt_index = max((i for i, line in enumerate(lines) if line.strip().startswith("›")), default=-1)

    attention_markers = (
        "press enter to continue",
        "approval requested",
        "requires approval",
        "permission requested",
        "stream disconnected before completion",
    )
    working_markers = (
        "esc to interrupt",
        "working (",
        "codex is working",
        "searching the web",
        "running command",
        "waiting for background terminal",
        "thinking",
        "reading",
        "editing",
        "patching",
        "executing",
    )

    attention_index = max((i for i, line in enumerate(lowered) if any(marker in line for marker in attention_markers)), default=-1)
    working_index = max((i for i, line in enumerate(lowered) if any(marker in line for marker in working_markers)), default=-1)

    after_prompt = lines[prompt_index + 1 :] if prompt_index >= 0 else lines
    response_after_prompt = any(
        line.lstrip().startswith(("•", "◦", "■"))
        for line in after_prompt
        if "·" not in line and "gpt-" not in line.lower() and "token usage:" not in line.lower()
    )

    if attention_index > prompt_index:
        return "NEEDS_HUMAN"
    if working_index >= 0 or response_after_prompt:
        return "BUSY"
    if prompt_index >= 0:
        return "IDLE"
    return normalize_activity(str(agent.get("activity"))) if agent.get("activity") else None


def display_status(agent: dict[str, Any]) -> str:
    raw_status = str(agent.get("status") or "STOPPED").upper()
    if raw_status in {"FAILED", "STALLED"}:
        return raw_status

    inferred = infer_codex_activity(agent)
    if inferred == "BUSY":
        last_update = parse_time(agent.get("last_update"))
        stalled = (
            raw_status in ACTIVE_STATUSES
            and not agent.get("_pane_changing", False)
            and last_update is not None
            and (now_utc() - last_update).total_seconds() > stalled_timeout()
        )
        return "STALLED" if stalled else "BUSY"
    if inferred:
        return inferred

    status = effective_status(agent)
    return default_activity(status, bool(agent.get("needs_human", False)))


def load_agents() -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    with locked_agent_state() as state:
        state_agents = state.get("agents", {})
        if not isinstance(state_agents, dict):
            return []

        for agent_id in sorted(state_agents):
            stored = state_agents.get(agent_id)
            if not isinstance(stored, dict):
                continue

            data = dict(stored)
            data.setdefault("agent_id", agent_id)
            data["display_status"] = display_status(data)
            inferred_activity = normalize_activity(data["display_status"]) if data["display_status"] in ACTIVITIES else None

            if inferred_activity and (data.get("activity") != inferred_activity or data.get("_pane_changing", False)):
                data["activity"] = inferred_activity
                data["needs_human"] = inferred_activity == "NEEDS_HUMAN"
                data["last_update"] = iso_now()
                stored.update({"activity": data["activity"], "needs_human": data["needs_human"], "last_update": data["last_update"]})

            data["effective_status"] = effective_status(data)
            data.pop("_pane_changing", None)
            data.setdefault("activity", default_activity(data["effective_status"], bool(data.get("needs_human", False))))
            agents.append(data)
    return agents


def status_icon(status: str, count: int | None = None) -> str:
    color = STATUS_COLORS.get(status.upper(), STATUS_COLORS["NONE"])
    suffix = "" if count is None else f" {count}"
    return f"#[fg={color}]⬤#[default]{suffix}"


def window_status(args: argparse.Namespace) -> None:
    icons = []
    for agent in load_agents():
        agent_window_id = str(agent.get("window_id") or "").strip()
        agent_window = str(agent.get("window") or "").strip()
        if (args.window_id and agent_window_id == args.window_id) or (
            not agent_window_id and args.window and agent_window == args.window
        ):
            count = idea_file_count_for_pane(str(agent.get("pane", "")))
            icons.append(status_icon(str(agent.get("display_status", "NONE")), count))
    print(" ".join(icons))


def rows_for_display() -> list[list[str]]:
    rows = []
    for agent in load_agents():
        rows.append(
            [
                str(agent.get("agent_id", "")),
                str(agent.get("effective_status", agent.get("status", ""))),
                str(agent.get("activity", "")),
                str(agent.get("display_status", "")),
                "yes" if agent.get("needs_human") else "no",
                str(agent.get("window", "")),
                str(agent.get("window_id", "")),
                str(agent.get("pane", "")),
                str(agent.get("last_update", "")),
                str(agent.get("task", "")),
            ]
        )
    return rows


def print_table() -> None:
    headers = ["Agent", "Status", "Activity", "Display", "Human", "Window", "Window ID", "Pane", "Last update", "Task"]
    rows = rows_for_display()
    all_rows = [headers] + rows
    widths = [min(max(len(row[i]) for row in all_rows), 42 if i == 8 else 24) for i in range(len(headers))]

    def fmt(row: list[str]) -> str:
        cells = []
        for i, value in enumerate(row):
            value = value[: widths[i] - 3] + "..." if len(value) > widths[i] else value
            cells.append(value.ljust(widths[i]))
        return "  ".join(cells)

    print(fmt(headers))
    print(fmt(["-" * width for width in widths]))
    for row in rows:
        print(fmt(row))


def list_agents(args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(load_agents(), indent=2, sort_keys=True))
    else:
        print_table()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_update_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--agent", default=os.environ.get("AGENT_ID"), required=os.environ.get("AGENT_ID") is None)
        p.add_argument("--status", required=True)
        p.add_argument("--task")
        p.add_argument("--message")
        p.add_argument("--window")
        p.add_argument("--window-id")
        p.add_argument("--session")
        p.add_argument("--pane")
        p.add_argument("--needs-human", type=bool_arg, nargs="?", const=True)
        p.add_argument("--activity", choices=["idle", "busy", "needs-human", "needs_human", "IDLE", "BUSY", "NEEDS_HUMAN"])

    register_parser = sub.add_parser("register")
    add_update_args(register_parser)
    register_parser.set_defaults(func=lambda args: upsert_agent(args, register=True))

    update_parser = sub.add_parser("update")
    add_update_args(update_parser)
    update_parser.set_defaults(func=lambda args: upsert_agent(args, register=False))

    delete_parser = sub.add_parser("delete")
    delete_parser.add_argument("--agent", default=os.environ.get("AGENT_ID"), required=os.environ.get("AGENT_ID") is None)
    delete_parser.set_defaults(func=delete_agent)

    prune_parser = sub.add_parser("prune")
    prune_parser.add_argument("--failed", action="store_true", help="also remove failed agents")
    prune_parser.set_defaults(func=prune_agents)

    codex_hook_parser = sub.add_parser("codex-hook")
    codex_hook_parser.add_argument("--event", required=True)
    codex_hook_parser.add_argument("--agent", default="")
    codex_hook_parser.set_defaults(func=codex_hook)

    window_status_parser = sub.add_parser("window-status")
    window_status_parser.add_argument("--window-id", default="")
    window_status_parser.add_argument("--window", default="")
    window_status_parser.set_defaults(func=window_status)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=list_agents)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
