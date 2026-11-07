"""Best-effort outbound Telegram message archive to a private GitHub repository.

Disabled unless TELEGRAM_ARCHIVE_GITHUB_TOKEN is set. Network requests happen
in a daemon thread and do not delay trade or prediction processing.
"""
import base64
import datetime as dt
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

_TOKEN = os.environ.get("TELEGRAM_ARCHIVE_GITHUB_TOKEN", "").strip()
_REPO = os.environ.get("TELEGRAM_ARCHIVE_REPO", "munky46861986/telegram-messages-private.").strip()
_QUEUE = queue.Queue(maxsize=10000)
_THREAD = None
_LOCK = threading.Lock()


def _api(method, path, payload=None):
    url = "https://api.github.com/repos/" + urllib.parse.quote(_REPO, safe="/.-") + "/contents/" + urllib.parse.quote(path, safe="/")
    headers = {
        "Authorization": "Bearer " + _TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bot-message-private-archive",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def _write(event):
    source = event["source"]
    stamp = dt.datetime.fromisoformat(event["at"])
    path = f"messages/{source}/{stamp:%Y/%m/%d/%H}.jsonl"
    entry = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    for _ in range(7):
        try:
            existing = _api("GET", path)
            sha = existing.get("sha")
            raw = base64.b64decode(existing.get("content", "")).decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            sha, raw = None, ""
        if '"id":"' + event["id"] + '"' in raw:
            return
        encoded = base64.b64encode((raw + entry).encode("utf-8")).decode("ascii")
        payload = {"message": "Archive " + source + " Telegram notification", "content": encoded}
        if sha:
            payload["sha"] = sha
        try:
            _api("PUT", path, payload)
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422):
                raise
            time.sleep(0.5)
    raise RuntimeError("GitHub archive write conflict")


def _worker():
    while True:
        event = _QUEUE.get()
        try:
            delay = 3
            while True:
                try:
                    _write(event)
                    break
                except Exception as exc:
                    print("TELEGRAM ARCHIVE RETRY:", type(exc).__name__)
                    time.sleep(delay)
                    delay = min(delay * 2, 180)
        finally:
            _QUEUE.task_done()


def archive_message(source, text):
    """Queue a successfully sent Telegram text without blocking its sender."""
    global _THREAD
    if not _TOKEN or not text or source not in ("superambo3", "gold-master"):
        return
    item = {
        "id": uuid.uuid4().hex,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "source": source,
        "direction": "bot_to_user",
        "text": str(text),
    }
    try:
        _QUEUE.put_nowait(item)
        if _THREAD is None:
            with _LOCK:
                if _THREAD is None:
                    _THREAD = threading.Thread(target=_worker, daemon=True, name="telegram-archive")
                    _THREAD.start()
    except queue.Full:
        print("TELEGRAM ARCHIVE WARNING: local queue full; message not archived")
