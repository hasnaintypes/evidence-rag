import threading
import time
from collections import deque
from typing import Dict

from fastapi import HTTPException

from src.core.config import settings

# --------------------------------------------------------------------------- #
# Per-user sliding-window rate limiting
#
# Protects the two routes that actually spend Gemini quota per call -
# POST /conversations/{id}/messages (query rewrite, embedding, grading,
# generation, faithfulness judging - several Gemini calls per turn) and
# POST /upload (one embedding call per chunk, so a large document is
# already a burst) - from a single caller looping/retrying fast enough to
# exhaust the app's daily quota (see #10/#24 - this project has already
# hit a free-tier 20-requests/day cap once).
#
# Scoped by user_id, not IP: every route with a real Gemini cost sits
# behind get_current_user, so there's no meaningful unauthenticated attack
# surface to cover (the two routes that skip auth, /health and
# /source/{filename}, don't call Gemini at all). user_id is also the
# right unit for "a single client" regardless of how many IPs/devices
# that account uses.
#
# A sliding window (deque of request timestamps per key, oldest trimmed
# off the front) rather than a fixed-bucket counter, so a burst that
# straddles a window boundary (e.g. N requests just before the bucket
# resets, N more just after) can't double the effective limit within a
# short span - each request's allowance is evaluated against the actual
# trailing window, not a wall-clock-aligned bucket.
#
# In-memory/per-process only, same limitation as src/response_cache.py
# and retrieval/hybrid.py's index cache - a multi-worker/multi-instance
# deployment would give each process its own independent limit instead of
# a shared one (so the *effective* limit scales up with worker count).
# Fine for today's single-process deployment; revisit alongside the
# horizontal-scaling work tracked in #20 if this ever needs to be shared
# (a shared store, e.g. Redis, would be the natural next step).
# --------------------------------------------------------------------------- #

# {"<scope>:<user_id>": deque([timestamp, ...])}
_requests: Dict[str, deque] = {}
_lock = threading.Lock()

# Trimming a key's own deque on every call to it (below) only cleans up a
# user who keeps calling - it does nothing for a user_id that makes one
# request and is never seen again, since nothing revisits that key to
# trim it. Left alone, _requests would grow by one entry per distinct
# user_id ever seen for the life of the process, not just per
# concurrently-active user. A full-dict sweep on every single call would
# fix that but cost O(n) per request; instead, sweep only every
# _SWEEP_EVERY calls, amortizing that cost across many requests while
# still bounding memory to roughly "users seen in the last _SWEEP_EVERY
# calls' worth of wall-clock time" rather than "users ever seen."
_SWEEP_EVERY = 500
_calls_since_sweep = 0


def _sweep_expired(window_seconds: int) -> None:
    """Drops every key whose entire deque has aged out of the window.
    Must be called with _lock already held. A single global cutoff is
    correct even though chat/upload have different max_requests, because
    both scopes share the same rate_limit_window_seconds setting."""
    cutoff = time.time() - window_seconds
    for key in list(_requests.keys()):
        timestamps = _requests[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if not timestamps:
            del _requests[key]


def _check(scope: str, user_id: str, max_requests: int, window_seconds: int) -> None:
    """
    Raises HTTPException(429) if `user_id` has already made
    `max_requests` calls to `scope` within the trailing `window_seconds`;
    otherwise records this call and returns normally.
    """
    if not settings.rate_limit_enabled:
        return

    global _calls_since_sweep

    key = f"{scope}:{user_id}"
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        _calls_since_sweep += 1
        if _calls_since_sweep >= _SWEEP_EVERY:
            _calls_since_sweep = 0
            _sweep_expired(window_seconds)

        timestamps = _requests.setdefault(key, deque())
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            retry_after = max(1, int(timestamps[0] + window_seconds - now) + 1)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: at most {max_requests} requests per "
                    f"{window_seconds}s for this operation. Try again in {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


def enforce_chat_rate_limit(user_id: str) -> None:
    """Call-site for POST /conversations/{id}/messages."""
    _check("chat", user_id, settings.rate_limit_chat_max_requests, settings.rate_limit_window_seconds)


def enforce_upload_rate_limit(user_id: str) -> None:
    """Call-site for POST /upload."""
    _check("upload", user_id, settings.rate_limit_upload_max_requests, settings.rate_limit_window_seconds)


def clear_rate_limits() -> None:
    """Test/debug helper - drops every tracked request timestamp and
    resets the sweep counter."""
    global _calls_since_sweep
    with _lock:
        _requests.clear()
        _calls_since_sweep = 0
