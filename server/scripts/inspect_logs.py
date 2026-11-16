"""
Human-readable inspection of the structured logs under LOG_DIRECTORY
(src/core/logging_config.py, default ./logs) - built so a developer never
has to manually grep hundreds of raw JSONL lines to answer "how many AI
calls did this chat message make, and why."

Reads only - never writes to the log files. Stdlib-only (argparse + json),
no new dependency, consistent with every other scripts/*.py CLI here.

Usage:
    python scripts/inspect_logs.py chats --last 20
    python scripts/inspect_logs.py session <chat-session-id>
    python scripts/inspect_logs.py request <request-id>
    python scripts/inspect_logs.py stats --today
    python scripts/inspect_logs.py errors --last 20 [--verbose]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings  # noqa: E402


def _read_jsonl(path: str) -> list:
    """Returns every parseable JSON object in `path`, oldest first, in
    file order. Missing file -> empty list (e.g. nothing's been logged
    to that category yet) rather than an error - this is a read-only
    inspection tool, not something that should fail just because the app
    hasn't run yet today."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a rotation mid-write can leave a partial trailing line - skip it, don't crash
    return rows


def _category_path(category: str) -> str:
    return {
        "chat": os.path.join(settings.log_directory, "chat", "requests.jsonl"),
        "ai": os.path.join(settings.log_directory, "ai", "invocations.jsonl"),
        "app": os.path.join(settings.log_directory, "application", "app.jsonl"),
        "errors": os.path.join(settings.log_directory, "errors", "errors.jsonl"),
    }[category]


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except (ValueError, AttributeError):
        return ts or "?"


def cmd_chats(args) -> None:
    rows = _read_jsonl(_category_path("chat"))
    rows = [r for r in rows if r.get("event", "").startswith("chat.request.")]
    for row in rows[-args.last :]:
        print(
            f"{_fmt_ts(row.get('timestamp'))}  "
            f"request={row.get('request_id', '?'):<14} "
            f"outcome={row.get('outcome', '?'):<18} "
            f"duration={row.get('total_duration_ms', 0):>7.1f}ms "
            f"ai_calls={row.get('ai_invocations', 0)} "
            f"retries={row.get('ai_retries', 0)} "
            f"fallbacks={row.get('ai_fallbacks', 0)} "
            f"cache_hit={row.get('cache_hit')}"
        )
    if not rows:
        print(f"No chat request summaries found in {_category_path('chat')}.")


def cmd_session(args) -> None:
    session_id = args.session_id
    chat_rows = [r for r in _read_jsonl(_category_path("chat")) if r.get("chat_session_id") == session_id]
    ai_rows = [r for r in _read_jsonl(_category_path("ai")) if r.get("chat_session_id") == session_id]

    print(f"=== Chat summaries for session {session_id} ===")
    for row in chat_rows:
        print(f"{_fmt_ts(row.get('timestamp'))}  request={row.get('request_id')}  outcome={row.get('outcome')}")

    print(f"\n=== AI invocations for session {session_id} ===")
    for row in ai_rows:
        if not row.get("event", "").startswith("ai.invocation."):
            continue
        print(
            f"{_fmt_ts(row.get('timestamp'))}  {row.get('event'):<24} "
            f"provider={row.get('provider'):<10} model={row.get('model'):<24} "
            f"operation={row.get('operation'):<22} duration={row.get('duration_ms', '?')}ms"
        )
    if not chat_rows and not ai_rows:
        print("(nothing found - check LOG_DIRECTORY and that this session id matches a real conversation id)")


def cmd_request(args) -> None:
    request_id = args.request_id

    chat_match = next((r for r in _read_jsonl(_category_path("chat")) if r.get("request_id") == request_id), None)
    ai_matches = [r for r in _read_jsonl(_category_path("ai")) if r.get("request_id") == request_id]
    # observability.py's traced_stage() logs through plain stdlib %-style
    # args ("stage_start request_id=%s stage=%s"), so by the time it
    # reaches app.jsonl the whole thing is one formatted string in the
    # "event" field, not a structured request_id key - substring match
    # is the only way to find these lines.
    stage_matches = [r for r in _read_jsonl(_category_path("app")) if f"request_id={request_id} " in r.get("event", "")]

    timeline = []
    for r in stage_matches:
        timeline.append((r.get("timestamp", ""), r.get("event", "")))
    for r in ai_matches:
        timeline.append(
            (r.get("timestamp", ""), f"{r.get('event')} provider={r.get('provider')} operation={r.get('operation')}")
        )
    timeline.sort(key=lambda t: t[0])

    print(f"=== Timeline for request {request_id} ===")
    for ts, line in timeline:
        print(f"{_fmt_ts(ts)}  {line}")

    if chat_match:
        print("\n=== Summary ===")
        for key in (
            "outcome",
            "total_duration_ms",
            "stage_breakdown_ms",
            "ai_invocations",
            "ai_http_attempts",
            "ai_retries",
            "ai_fallbacks",
            "ai_errors",
            "ai_calls_by_provider_operation",
            "input_tokens",
            "output_tokens",
            "cache_hit",
            "injection_flags_count",
        ):
            print(f"  {key}: {chat_match.get(key)}")
    else:
        print(
            "\n(no chat.request.* summary found for this request_id - it may still be in flight, or LOG_CHAT_SUMMARIES is off)"
        )


def cmd_stats(args) -> None:
    rows = _read_jsonl(_category_path("ai"))
    if args.today:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = [r for r in rows if str(r.get("timestamp", "")).startswith(today)]

    invocations = [
        r for r in rows if r.get("event") == "ai.invocation.completed" or r.get("event") == "ai.invocation.failed"
    ]
    cache_hits = sum(1 for r in rows if r.get("event") == "ai.cache_hit")
    cache_misses = sum(1 for r in rows if r.get("event") == "ai.cache_miss")

    by_key = defaultdict(
        lambda: {"count": 0, "errors": 0, "retries": 0, "fallbacks": 0, "input_tokens": 0, "output_tokens": 0}
    )
    for r in invocations:
        key = f"{r.get('provider')}:{r.get('operation')}"
        g = by_key[key]
        g["count"] += 1
        if r.get("event") == "ai.invocation.failed":
            g["errors"] += 1
        attempts = r.get("attempts", 1) or 1
        if attempts > 1:
            g["retries"] += attempts - 1
        if r.get("is_fallback"):
            g["fallbacks"] += 1
        g["input_tokens"] += r.get("input_tokens") or 0
        g["output_tokens"] += r.get("output_tokens") or 0

    label = "today" if args.today else "all time"
    print(f"=== AI usage stats ({label}) ===")
    print(f"Cache hits: {cache_hits}  Cache misses: {cache_misses}", end="")
    total_cache = cache_hits + cache_misses
    if total_cache:
        print(f"  (hit rate {cache_hits / total_cache:.0%})")
    else:
        print()
    print()
    print(
        f"{'provider:operation':<32} {'count':>6} {'errors':>7} {'retries':>8} {'fallbacks':>10} {'in_tok':>8} {'out_tok':>8}"
    )
    for key, g in sorted(by_key.items()):
        print(
            f"{key:<32} {g['count']:>6} {g['errors']:>7} {g['retries']:>8} {g['fallbacks']:>10} "
            f"{g['input_tokens']:>8} {g['output_tokens']:>8}"
        )
    if not by_key:
        print("(no AI invocations logged yet)")


def cmd_errors(args) -> None:
    rows = _read_jsonl(_category_path("errors"))
    for row in rows[-args.last :]:
        print(f"{_fmt_ts(row.get('timestamp'))}  [{row.get('logger')}] {row.get('event')}")
        if args.verbose and row.get("exception"):
            print(row["exception"])
    if not rows:
        print(f"No errors found in {_category_path('errors')}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_chats = sub.add_parser("chats", help="Show recent chat request summaries")
    p_chats.add_argument("--last", type=int, default=20)
    p_chats.set_defaults(func=cmd_chats)

    p_session = sub.add_parser("session", help="Show every chat summary + AI call for one chat session id")
    p_session.add_argument("session_id")
    p_session.set_defaults(func=cmd_session)

    p_request = sub.add_parser("request", help="Show the full stage timeline + AI calls for one request id")
    p_request.add_argument("request_id")
    p_request.set_defaults(func=cmd_request)

    p_stats = sub.add_parser("stats", help="Show aggregated AI usage statistics")
    p_stats.add_argument("--today", action="store_true", help="Restrict to today (UTC) only")
    p_stats.set_defaults(func=cmd_stats)

    p_errors = sub.add_parser("errors", help="Show recent errors")
    p_errors.add_argument("--last", type=int, default=20)
    p_errors.add_argument("--verbose", action="store_true", help="Include the full exception traceback")
    p_errors.set_defaults(func=cmd_errors)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
