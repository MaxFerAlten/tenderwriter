"""Transcript Forwarder — watch Jigasi transcript folder and post to Mattermost via Incoming Webhook.

Usage (standalone):
    python transcript_forwarder.py --watch-dir /tmp/transcripts --webhook-url https://mattermost.example.com/hooks/xxx

Usage (Docker sidecar):
    Mount the jitsi_transcripts volume and run this script inside the container.

Environment variables (override CLI args):
    TRANSCRIPT_WATCH_DIR   — directory to watch for new .vtt/.txt files
    MM_WEBHOOK_URL         — Mattermost Incoming Webhook URL
    POLL_INTERVAL_SECONDS  — polling interval (default: 5)
    TRANSCRIPT_STABLE_SECONDS — seconds a file must remain unchanged before it is forwarded
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


SUPPORTED_SUFFIXES = (".vtt", ".txt", ".json", ".srt")


@dataclass
class ObservedTranscript:
    size: int
    mtime: float
    last_change: float
    existed_at_startup: bool
    changed_since_startup: bool = False


def is_supported_transcript(filepath: Path) -> bool:
    return filepath.is_file() and filepath.suffix.lower() in SUPPORTED_SUFFIXES


def snapshot_transcript(filepath: Path) -> tuple[int, float] | None:
    try:
        stat = filepath.stat()
    except OSError as exc:
        print(f"[WARN] Cannot stat {filepath}: {exc}", file=sys.stderr)
        return None
    return stat.st_size, stat.st_mtime


def read_transcript(filepath: Path) -> str:
    """Read a transcript file (.vtt or .txt) and return its text content."""
    try:
        return filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[WARN] Cannot read {filepath}: {exc}", file=sys.stderr)
        return ""


def post_to_mattermost(webhook_url: str, text: str, filename: str) -> bool:
    """Post a transcript message to Mattermost via Incoming Webhook."""
    payload = {
        "username": "Jitsi Transcription Bot",
        "icon_url": "https://jitsi.org/wp-content/uploads/2location/09/jitsi1.png",
        "text": f"### Trascrizione videochiamata\n"
                f"**File:** `{filename}`\n"
                f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"---\n\n"
                f"```\n{text[:15000]}\n```",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError) as exc:
        print(f"[ERROR] Failed to post to Mattermost: {exc}", file=sys.stderr)
        return False


def watch_and_forward(
    watch_dir: Path,
    webhook_url: str,
    poll_interval: int = 5,
    stable_seconds: int = 20,
) -> None:
    """Poll watch_dir for transcript files and forward them to Mattermost once stable."""
    processed: set[str] = set()
    observed: dict[str, ObservedTranscript] = {}
    startup_seen = 0

    if watch_dir.exists():
        now = time.time()
        for f in watch_dir.iterdir():
            if not is_supported_transcript(f):
                continue
            snapshot = snapshot_transcript(f)
            if snapshot is None:
                continue
            size, mtime = snapshot
            observed[f.name] = ObservedTranscript(
                size=size,
                mtime=mtime,
                last_change=now,
                existed_at_startup=True,
            )
            startup_seen += 1

    print(f"[INFO] Watching {watch_dir} for new transcripts (poll every {poll_interval}s)")
    print(f"[INFO] Mattermost webhook: {webhook_url[:40]}...")
    print(f"[INFO] Files must stay unchanged for {stable_seconds}s before forwarding")
    print(f"[INFO] {startup_seen} existing transcript file(s) tracked at startup")

    while True:
        try:
            if not watch_dir.exists():
                time.sleep(poll_interval)
                continue

            now = time.time()
            for filepath in sorted(watch_dir.iterdir()):
                if not is_supported_transcript(filepath):
                    continue

                snapshot = snapshot_transcript(filepath)
                if snapshot is None:
                    continue
                size, mtime = snapshot

                state = observed.get(filepath.name)
                if state is None:
                    observed[filepath.name] = ObservedTranscript(
                        size=size,
                        mtime=mtime,
                        last_change=now,
                        existed_at_startup=False,
                        changed_since_startup=True,
                    )
                    print(f"[INFO] New transcript detected: {filepath.name}")
                    continue

                if size != state.size or mtime != state.mtime:
                    state.size = size
                    state.mtime = mtime
                    state.last_change = now
                    state.changed_since_startup = True
                    continue

                if filepath.name in processed:
                    continue
                if state.existed_at_startup and not state.changed_since_startup:
                    continue
                if now - state.last_change < stable_seconds:
                    continue

                text = read_transcript(filepath)

                if not text.strip():
                    print(f"[WARN] Empty transcript, skipping: {filepath.name}")
                    processed.add(filepath.name)
                    continue

                success = post_to_mattermost(webhook_url, text, filepath.name)
                if success:
                    print(f"[OK] Forwarded to Mattermost: {filepath.name}")
                else:
                    print(f"[FAIL] Will retry next cycle: {filepath.name}")
                    continue  # don't mark as processed, retry next cycle

                processed.add(filepath.name)

        except KeyboardInterrupt:
            print("\n[INFO] Shutting down transcript forwarder.")
            break
        except Exception as exc:
            print(f"[ERROR] Unexpected: {exc}", file=sys.stderr)

        time.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward Jitsi/Jigasi transcripts to Mattermost")
    parser.add_argument("--watch-dir", default=None, help="Directory to watch for transcript files")
    parser.add_argument("--webhook-url", default=None, help="Mattermost Incoming Webhook URL")
    parser.add_argument("--poll-interval", type=int, default=None, help="Polling interval in seconds")
    parser.add_argument(
        "--stable-seconds",
        type=int,
        default=None,
        help="Seconds a transcript must stay unchanged before being forwarded",
    )
    args = parser.parse_args()

    watch_dir = Path(args.watch_dir or os.environ.get("TRANSCRIPT_WATCH_DIR", "/tmp/transcripts"))
    webhook_url = args.webhook_url or os.environ.get("MM_WEBHOOK_URL", "")
    poll_interval = args.poll_interval or int(os.environ.get("POLL_INTERVAL_SECONDS", "5"))
    stable_seconds = args.stable_seconds or int(os.environ.get("TRANSCRIPT_STABLE_SECONDS", "20"))

    if not webhook_url:
        print("[FATAL] No Mattermost webhook URL provided. Use --webhook-url or MM_WEBHOOK_URL env var.", file=sys.stderr)
        sys.exit(1)

    watch_and_forward(watch_dir, webhook_url, poll_interval, stable_seconds)


if __name__ == "__main__":
    main()
