"""実行途中の結果を残しておく一時キャッシュ。

run.py が途中で失敗（APIエラー・例外・中止）しても、再実行時に取得済みの記事本文や
生成済みの要約を取り直さずに済むようにする。手作業で貼り付けた本文もここに残る。
保存先は work/（.gitignore対象）。古いエントリは自動で捨てる。
"""
import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join("work", "podcast_run_cache.json")
MAX_AGE_SECONDS = 3 * 24 * 60 * 60


class RunCache:
    def __init__(self, path=CACHE_PATH, enabled=True):
        self.path = path
        self.enabled = enabled
        self.data = {}
        if not enabled:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            now = time.time()
            self.data = {k: v for k, v in loaded.items() if now - v.get("saved_at", 0) < MAX_AGE_SECONDS}
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning(f"キャッシュを読めなかったため作り直します: {e}")

    @staticmethod
    def key(*parts):
        joined = "\x00".join(str(p or "") for p in parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]

    def get(self, key, name):
        return self.data.get(key, {}).get(name)

    def set(self, key, name, value):
        if not self.enabled:
            return
        entry = self.data.setdefault(key, {})
        entry[name] = value
        entry["saved_at"] = time.time()
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:
            logger.warning(f"キャッシュを保存できませんでした: {e}")
