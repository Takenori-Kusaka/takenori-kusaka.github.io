"""URLから記事本文だけを取り出す。

取得の流れ:
1. 通常のHTTP取得（静的HTML）で本文抽出を試みる。PDF・プレーンテキストにも対応
2. 本文が十分に取れなければ、ヘッドレスブラウザでJavaScriptレンダリング後のHTMLを取得して再抽出する
3. 複数ページに分かれた記事は「次のページ」をたどって結合する

本文の開始・終了の判定と、広告・ナビゲーション・関連記事・コメント欄の除去は trafilatura に任せる。
うまく取れなかった場合は必ず原因を切り分けて Article.problem / Article.detail に入れて返す
（URLの指定ミスなのか、サイト側の拒否なのか、取得ロジック側の限界なのか）。

単体での確認:
    python src/article_extractor.py <URL>

利用確認画面やログインが必要なサイト（NHK ONE、有料会員記事など）は、画面付きブラウザで一度
手動操作すると、その状態が専用プロファイルに保存され、以後は自動取得できる
（run.py 実行中に必要になった場合はコンソールで尋ねられる）:
    python src/article_extractor.py --login <URL>
"""
import html as html_lib
import io
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import trafilatura

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# これ未満しか取れない場合は取得ミスの可能性が高いとみなす（ブラウザで取り直し、それでも短ければ要確認）
MIN_BODY_CHARS = 300
# 省略記号で終わっていても、これ以上の長さがあれば「途中で切られた」とはみなさない
TRUNCATION_CHECK_MAX_CHARS = 1000
# 複数ページ記事でたどるページ数の上限
MAX_PAGES = 10
# ダウンロードする最大サイズ（動画などの巨大ファイルを誤って指定された場合の保険）
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
# レンダリング時に読み込まないリソース（本文抽出に不要で、遅延と広告の原因になる）
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
# Cookie等を保持する専用ブラウザプロファイル（認証情報を含むためリポジトリの外に置く）
PROFILE_DIR = Path(os.environ.get("ARTICLE_BROWSER_PROFILE", Path.home() / ".podcast_article_browser"))
# ログイン・利用確認を済ませたホストの一覧（これらは最初からブラウザで取得する）
LOGIN_HOSTS_FILE = PROFILE_DIR / "login_hosts.txt"

# 記事ではなくブロック画面を掴んだときに現れる文言（小文字で比較）
BLOCK_PAGE_MARKERS = (
    "not a robot", "are you a robot", "verify you are human", "captcha",
    "enable javascript", "supports javascript and cookies", "access denied",
    "just a moment", "unusual activity", "ロボットではない", "アクセスが拒否",
    "javascriptを有効", "コンテンツブロック", "広告ブロック", "adblock", "ad blocker", "お住まいの地域", "not available in your region", "not available in your country",
)
# HTTP 200で返ってくる「ページがありません」画面（ソフト404）
SOFT_404_RE = re.compile(
    r"404|not\s*found|ページ(が|は)?(見つかりません|みつかりません|存在しません)|お探しのページ|"
    r"(記事|ページ)(は|が)?削除|掲載(期間)?(が|は)?終了|公開(期間)?(が|は|を)?終了|配信(期間)?(が|は)?終了",
    re.IGNORECASE,
)
# 有料・会員限定で本文が途中までしか配信されていないことを示す表示
PAYWALL_RE = re.compile(
    r"残り\s*[\d,，]+\s*文字|この記事は(有料)?会員限定|有料会員限定記事|この記事は有料記事|"
    r"(ログイン|会員登録|無料登録)(して|すると)(続き|全文)|(続き|全文)を読むには|"
    r"subscribe to (continue|keep) reading|to continue reading",
    re.IGNORECASE,
)
JSONLD_PAYWALL_RE = re.compile(r"\"isAccessibleForFree\"\s*:\s*\"?false", re.IGNORECASE)
JSONLD_PAYWALL_MAX_CHARS = 800
# ブラウザ取得時、本文抽出の邪魔になるCookie同意バナー等を取り除く
REMOVE_OVERLAYS_JS = """
() => {
  const sel = '[id*="onetrust" i], [id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i], [id*="gdpr" i], [class*="gdpr" i]';
  for (const el of document.querySelectorAll(sel)) {
    if (el !== document.body && el !== document.documentElement && !el.querySelector('article, main')) el.remove();
  }
}
"""
# 本文が途中で打ち切られていることを示す行末（省略記号、「続きを読む」リンク）
TRUNCATED_LINE_RE = re.compile(r"(…|\.\.\.|続きを読む|続きを見る|もっと読む|全文を読む|read more|continue reading)\s*$", re.IGNORECASE)
LOGIN_PATH_RE = re.compile(r"/(login|signin|sign[-_]in|sso|auth|consent|register)(/|\.|\?|$)", re.IGNORECASE)
NEXT_LABEL_RE = re.compile(r"^(次へ|次のページへ?|次ページへ?|続きを読む|next(\s*page)?)\s*[»>›→＞]*$", re.IGNORECASE)
# 本文の後ろに付く定型の見出し（ここから先は関連記事の一覧なので捨てる）
TAIL_HEADING_RE = re.compile(
    r"^[【\[]?(関連記事|関連リンク|関連するニュース|あわせて読みたい|こんな記事も読まれています|おすすめ記事|人気記事)[】\]]?$"
)
TAIL_NOISE_RE = re.compile(
    r"^(copyright\b.*|©.*|\(c\)\s*\d{4}.*|ツイート|シェアする|すべての画像|この記事の目次へ戻る|各地のニュース|地図から選ぶ)$",
    re.IGNORECASE,
)
NON_ARTICLE_TYPES = ("image/", "video/", "audio/", "font/", "application/zip", "application/octet-stream",
                     "application/x-", "application/vnd.", "application/msword", "application/json")

# Article.problem の値
PROBLEM_URL = "url"          # URLの指定ミス（書式不正・存在しない・削除済み・トップへ転送）
PROBLEM_BLOCKED = "blocked"  # サイト側に拒否された（ボット対策・地域制限など）
PROBLEM_NETWORK = "network"  # 接続できない・サーバーエラー（一時的な可能性）
PROBLEM_EMPTY = "empty"      # ページは開けたが本文を見つけられない（記事形式でない／取得ロジック側）
PROBLEM_RAW = "raw"          # 本文領域を特定できず、ページ全体のテキストで代用した
PROBLEM_PARTIAL = "partial"  # 本文が短い・途中で切れている（ログイン壁・有料記事か、もともと短い記事）


@dataclass
class Article:
    url: str
    title: str = ""
    text: str = ""
    method: str = ""   # "static" / "browser" / "pdf" / "oembed" / "manual"
    problem: str = ""  # 問題がなければ空。あれば PROBLEM_* のいずれか
    detail: str = ""   # problem の説明（人が読む用）
    pages: int = 1

    @property
    def ok(self):
        return bool(self.text) and not self.problem


@dataclass
class _Response:
    data: bytes = b""
    html: str = ""            # ブラウザ取得: スクロール前のHTML
    html_scrolled: str = ""   # ブラウザ取得: 最下部までスクロールした後のHTML
    raw_text: str = ""        # ブラウザ取得: 画面に見えている全テキスト
    status: int = 0
    final_url: str = ""
    content_type: str = ""
    error: str = ""           # "dns" / "ssl" / "timeout" / "toolarge" / "network" / ""
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------- URLの検査

def normalize_url(url):
    """topic.yamlに書かれたURLを整える。(URL, エラー説明) を返す"""
    url = (url or "").strip().strip("<>「」『』\"'　")
    if not url:
        return "", "URLが空です"
    if re.search(r"\s", url):
        return "", "URLの途中に空白や改行があります（link欄にURL以外の文字が入っていないか確認してください）"
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "", f"http/https以外のURLです（{parsed.scheme}）"
    if "." not in parsed.netloc:
        return "", f"ホスト名が正しくありません（{parsed.netloc or '空'}）"
    return url, ""


# ---------------------------------------------------------------- 本文抽出

def _decode(data):
    if isinstance(data, str):
        return data
    try:
        return trafilatura.utils.decode_file(data) or ""
    except Exception:
        return data.decode("utf-8", errors="replace")


def _clean_tail(text):
    """本文の後ろに残った関連記事の見出し・著作権表示・共有ボタンの文言を落とす"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # 記事の後半に現れた「関連記事」見出し以降は本文ではない
        if i >= max(3, len(lines) // 2) and TAIL_HEADING_RE.match(line.strip()):
            lines = lines[:i]
            break
    lines = [l for l in lines if not TAIL_NOISE_RE.match(l.strip())]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _extract(html, url):
    """HTMLから(タイトル, 本文)を抽出する。取れなければ ("", "")"""
    if not html:
        return "", ""
    # まず精度優先（本文以外を厳しく落とす）。それで本文をほとんど拾えないページだけ標準設定で取り直す
    title, text = _extract_once(html, url, favor_precision=True)
    if len(text) < MIN_BODY_CHARS:
        t2, text2 = _extract_once(html, url, favor_precision=False)
        if len(text2) > len(text):
            title, text = t2 or title, text2
    if _is_consent_text(text):
        return title, ""
    return title, text


def _extract_once(html, url, favor_precision):
    try:
        doc = trafilatura.bare_extraction(
            html,
            url=url,
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            favor_precision=favor_precision,
            deduplicate=True,
        )
    except Exception as e:
        logger.warning(f"本文抽出エラー: {e}")
        return "", ""
    if doc is None:
        return "", ""
    if isinstance(doc, dict):
        title, text = doc.get("title"), doc.get("text")
    else:
        title, text = getattr(doc, "title", ""), getattr(doc, "text", "")
    return (title or "").strip(), _clean_tail((text or "").strip())


def _is_consent_text(text):
    """記事ではなくCookie同意バナーの説明文を本文として拾っていないか"""
    return len(text) < 4000 and text.lower().count("cookie") >= 3


def _extract_pdf(data):
    """PDFのバイト列から(タイトル, 本文)を抽出する"""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdfが未インストールのためPDFを読めません（pip install pypdf）")
        return "", ""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        title = (reader.metadata.title if reader.metadata else "") or ""
        return title.strip(), text
    except Exception as e:
        logger.warning(f"PDF抽出エラー: {e}")
        return "", ""


def _is_block_page(text):
    """ロボット確認・アクセス拒否など、記事ではなくブロック画面を掴んでいないか"""
    if not text or len(text) > 2000:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in BLOCK_PAGE_MARKERS)


def _looks_truncated(text):
    """「続きを読む」型で本文が途中で切られている兆候（短い本文が省略記号で終わる）があるか"""
    if len(text) >= TRUNCATION_CHECK_MAX_CHARS:
        return False
    return any(TRUNCATED_LINE_RE.search(line.rstrip()) for line in text.splitlines()[-6:])


def _is_soft_404(title, text):
    """HTTP 200で返る「ページがありません」画面か"""
    if title and SOFT_404_RE.search(title):
        return True
    return len(text) < 600 and bool(SOFT_404_RE.search(text[:300]))


def _paywall_hint(html, text):
    """有料・会員限定で途中までしか見えていないことを示す表示があれば、その文言を返す"""
    visible = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", html or "", flags=re.S | re.I)
    m = PAYWALL_RE.search(text[-400:]) or PAYWALL_RE.search(visible)
    if m:
        return m.group(0)
    # 構造化データの「無料では全文を読めない」印。従量制の媒体は全文が見えていても付けるので、短い本文のときだけ使う
    if len(text) < JSONLD_PAYWALL_MAX_CHARS and JSONLD_PAYWALL_RE.search(html or ""):
        return "isAccessibleForFree=false"
    return ""


def _redirected_to_top(url, final_url):
    """記事URLを指定したのにトップページへ転送されたか（削除済み・URL間違いの典型）"""
    if not final_url:
        return False
    return urlparse(url).path.strip("/") != "" and urlparse(final_url).path.strip("/") == ""


def _redirected_to_login(url, final_url):
    if not final_url:
        return False
    return bool(LOGIN_PATH_RE.search(urlparse(final_url).path)) and not LOGIN_PATH_RE.search(urlparse(url).path)


# ---------------------------------------------------------------- 複数ページ記事

def _same_article(first_url, next_url):
    """next_url が first_url と同じ記事の続きページか（別記事への「次の記事」リンクを除外する）"""
    a, b = urlparse(first_url), urlparse(next_url)
    if a.netloc != b.netloc:
        return False
    if a.path == b.path:
        return a.query != b.query and bool(re.search(r"(^|&)(page|p|pg|paged|pn)=\d+", b.query))
    stem = re.sub(r"(/index)?\.[a-z0-9]+$", "", a.path).rstrip("/")
    if not stem or not b.path.startswith(stem):
        return False
    rest = b.path[len(stem):]
    return bool(re.fullmatch(r"[/_-]?(page[/_-]?)?\d{1,2}(/|\.[a-z0-9]+)?", rest))


def _next_page_url(html, page_url, first_url):
    """HTMLから「次のページ」のURLを探す。無ければ None"""
    try:
        import lxml.html
        tree = lxml.html.fromstring(html)
    except Exception:
        return None
    candidates = tree.xpath("//link[contains(concat(' ', normalize-space(@rel), ' '), ' next ')]/@href")
    candidates += tree.xpath("//a[contains(concat(' ', normalize-space(@rel), ' '), ' next ')]/@href")
    for a in tree.xpath("//a[@href]"):
        label = " ".join(a.text_content().split())
        if label and len(label) <= 12 and NEXT_LABEL_RE.match(label):
            candidates.append(a.get("href"))
    for href in candidates:
        nxt = urljoin(page_url, href).split("#")[0]
        if nxt != page_url.split("#")[0] and _same_article(first_url, nxt):
            return nxt
    return None


def _fetch_page_html(url, use_browser):
    """続きのページのHTMLを取得する（1ページ目と同じ方法で）"""
    if use_browser:
        rendered = _fetch_rendered(url)
        return rendered.html if rendered.status == 200 else ""
    response = _fetch_static(url)
    return _decode(response.data) if response.status == 200 and response.data else ""


def _follow_pages(first_html, url, text, use_browser=False):
    """複数ページ記事の2ページ目以降を取得して結合する。(本文, ページ数) を返す"""
    pages, seen, html, page_url = 1, {url.split("#")[0]}, first_html, url
    while pages < MAX_PAGES:
        nxt = _next_page_url(html, page_url, url)
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        html = _fetch_page_html(nxt, use_browser)
        if not html:
            logger.warning(f"{pages + 1}ページ目を取得できませんでした: {nxt}")
            break
        _, more = _extract(html, nxt)
        if not more or more in text:
            break
        # 前ページと同じ導入文が繰り返されるサイトがあるため、重複する段落は除く
        known = set(text.splitlines())
        more = "\n".join(l for l in more.splitlines() if l not in known or not l.strip())
        text += "\n" + more
        pages += 1
        page_url = nxt
        logger.info(f"{pages}ページ目を結合しました: {nxt}")
    return text, pages


# ---------------------------------------------------------------- 取得

def _fetch_static(url, timeout=20):
    """通常のHTTP GETで取得する。一時的な失敗（タイムアウト・429・5xx）は1回だけ再試行する"""
    result = _Response()
    for attempt in range(2):
        if attempt:
            time.sleep(3)
        try:
            with requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
                timeout=timeout,
                stream=True,
            ) as response:
                result = _Response(
                    status=response.status_code,
                    final_url=response.url,
                    content_type=response.headers.get("content-type", "").split(";")[0].strip().lower(),
                )
                if result.content_type.startswith(("image/", "video/", "audio/")):
                    return result  # 本体は読まない
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        result.error = "toolarge"
                        return result
                result.data = b"".join(chunks)
            if result.status in (429, 500, 502, 503, 504):
                continue
            return result
        except requests.exceptions.SSLError as e:
            logger.warning(f"静的取得に失敗（証明書）: {e}")
            return _Response(error="ssl")
        except requests.exceptions.ConnectionError as e:
            # 名前解決の失敗は「ホスト名の打ち間違い」とほぼ同義
            if any(k in str(e) for k in ("NameResolution", "getaddrinfo", "Name or service")):
                return _Response(error="dns")
            logger.warning(f"静的取得に失敗: {e}")
            result = _Response(error="network")
        except requests.exceptions.Timeout:
            logger.warning("静的取得がタイムアウトしました")
            result = _Response(error="timeout")
        except requests.exceptions.RequestException as e:
            logger.warning(f"静的取得に失敗: {e}")
            return _Response(error="network")
    return result


def _launch(playwright, headless):
    """専用プロファイルでChromiumを起動する（ログイン済みの状態を引き継ぐ）"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        user_agent=USER_AGENT,
        locale="ja-JP",
        viewport={"width": 1280, "height": 2000 if headless else 900},
    )


def _fetch_rendered(url, timeout_ms=45000):
    """ヘッドレスChromiumでJavaScript実行後のHTMLを取得する"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwrightが未インストールのためブラウザ取得をスキップします"
                       "（pip install playwright && python -m playwright install chromium）")
        return _Response(error="network", notes=["playwright未インストール"])

    try:
        with sync_playwright() as p:
            context = _launch(p, headless=True)
            try:
                context.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                    else route.continue_(),
                )
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # 広告やトラッカーの通信が止まらないサイトがあるため、networkidleは待てるだけ待つ
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                result = _Response(status=response.status if response else 0)
                try:
                    page.evaluate(REMOVE_OVERLAYS_JS)
                except Exception:
                    pass
                # スクロールすると「次の記事」を継ぎ足すサイトがあるので、まずスクロール前を保存する
                result.html = page.content()
                for _ in range(8):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(250)
                try:
                    page.evaluate(REMOVE_OVERLAYS_JS)
                except Exception:
                    pass
                result.html_scrolled = page.content()
                try:
                    result.raw_text = page.inner_text("body", timeout=5000)
                except Exception:
                    pass
                result.final_url = page.url
                return result
            finally:
                context.close()
    except Exception as e:
        logger.warning(f"ブラウザ取得に失敗: {e}")
        kind = "timeout" if "Timeout" in type(e).__name__ else "network"
        return _Response(error=kind)


def _login_hosts():
    try:
        return set(LOGIN_HOSTS_FILE.read_text(encoding="utf-8").split())
    except OSError:
        return set()


def open_for_login(url):
    """画面付きブラウザでURLを開き、利用確認やログインを手動で済ませてもらう。

    セッション情報は専用プロファイルに残り、以後このホストはブラウザ経由で取得する。
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = _launch(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("ブラウザで利用確認・ログインを済ませ、記事本文が表示されたらウィンドウを閉じてください。")
        try:
            page.wait_for_event("close", timeout=0)
        finally:
            try:
                context.close()
            except Exception:
                pass
    hosts = _login_hosts() | {urlparse(url).netloc}
    LOGIN_HOSTS_FILE.write_text("\n".join(sorted(hosts)), encoding="utf-8")


def _fetch_tweet(url):
    """X(Twitter)の投稿は本体ページがログイン必須のため、公式の埋め込みAPIから本文を得る"""
    try:
        response = requests.get(
            "https://publish.twitter.com/oembed",
            params={"url": url, "omit_script": "1", "lang": "ja"},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if response.status_code == 404:
            return Article(url, problem=PROBLEM_URL, detail="投稿が存在しません（削除済みか、URLの指定ミスです）")
        response.raise_for_status()
        data = response.json()
        html = re.sub(r"<br\s*/?>", "\n", data.get("html", ""))
        m = re.search(r"<p[^>]*>(.*?)</p>", html, re.S)
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
        if text:
            author = data.get("author_name", "")
            return Article(url, f"{author} のX投稿" if author else "X投稿", text, "oembed")
    except Exception as e:
        logger.warning(f"X投稿の取得に失敗: {e}")
    return Article(url, problem=PROBLEM_BLOCKED,
                   detail="Xの投稿を取得できませんでした（非公開・年齢制限・ログイン必須の投稿の可能性）")


def _problem(url, problem, detail, **kwargs):
    logger.warning(f"{detail}: {url}")
    return Article(url, problem=problem, detail=detail, **kwargs)


def fetch_article(url, min_chars=MIN_BODY_CHARS):
    """URLから記事本文を取得する。

    必ず Article を返す。article.ok が False のときは article.problem / article.detail に
    原因の切り分け結果が入る（text に取れた範囲が入ることもある）。
    """
    original = url
    url, error = normalize_url(url)
    if error:
        return _problem(original, PROBLEM_URL, error)

    host = urlparse(url).netloc.lower()
    path = urlparse(url).path
    if host.removeprefix("www.").removeprefix("mobile.") in ("x.com", "twitter.com") and "/status/" in path:
        return _fetch_tweet(url)
    if host.removeprefix("www.").removeprefix("m.") in ("youtube.com", "youtu.be"):
        return _problem(url, PROBLEM_EMPTY,
                        "YouTubeの動画ページには記事本文がありません。URLの間違いではありませんが自動取得の対象外です"
                        "（動画の内容を貼り付けてください）")

    # ---- 通常取得
    static = _fetch_static(url)
    if static.error == "dns":
        return _problem(url, PROBLEM_URL, "ホスト名を解決できません。URLの打ち間違いの可能性が高いです")
    if static.error == "toolarge":
        return _problem(url, PROBLEM_EMPTY,
                        f"ファイルが大きすぎます（{MAX_DOWNLOAD_BYTES // 1024 // 1024}MB超）。記事ページではなくファイルのURLです")
    if static.status in (404, 410):
        return _problem(url, PROBLEM_URL,
                        f"ページが存在しません（HTTP {static.status}）。URLの指定ミスか、記事が削除されています")

    is_pdf = static.data.lstrip()[:5] == b"%PDF-" or static.content_type == "application/pdf"
    if is_pdf and static.data:
        title, text = _extract_pdf(static.data)
        logger.info(f"PDFからの本文: {len(text)}文字")
        if len(text) >= 50:
            return Article(url, title, text, "pdf")
        return _problem(url, PROBLEM_EMPTY,
                        "PDFは取得できましたが文字を取り出せませんでした（スキャン画像のPDFか、保護されたPDFです）")
    if static.status == 200 and static.content_type.startswith(NON_ARTICLE_TYPES):
        return _problem(url, PROBLEM_EMPTY,
                        f"記事ページではなくファイルのURLです（{static.content_type}）。URLは存在しますが本文はありません")
    if static.status == 200 and static.content_type == "text/plain":
        text = _decode(static.data).strip()
        if len(text) >= min_chars:
            return Article(url, "", text, "static")

    statuses = [f"通常取得 HTTP {static.status}" if static.status else f"通常取得 失敗({static.error})"]
    blocked = static.status in (401, 403, 429)
    static_html = _decode(static.data) if static.data else ""
    title, text = _extract(static_html, url)
    if _is_block_page(text):
        blocked, title, text = True, "", ""
    method, html, final_url, raw_text = "static", static_html, static.final_url, ""
    logger.info(f"静的取得での本文: {len(text)}文字")

    # ---- ブラウザ取得（本文不足・途中切れ・ログイン済みホストの場合）
    rendered = None
    if len(text) < min_chars or _looks_truncated(text) or host in _login_hosts():
        logger.info("ヘッドレスブラウザで再取得します")
        rendered = _fetch_rendered(url)
        statuses.append(f"ブラウザ取得 HTTP {rendered.status}" if rendered.status
                        else f"ブラウザ取得 失敗({rendered.error or '不明'})")
        if rendered.status in (404, 410):
            return _problem(url, PROBLEM_URL,
                            f"ページが存在しません（HTTP {rendered.status}）。URLの指定ミスか、記事が削除されています")
        # スクロール前で足りていればそれを使う（スクロールで継ぎ足された別記事の混入を避ける）
        r_title, r_text = _extract(rendered.html, url)
        r_html = rendered.html
        if len(r_text) < min_chars or _looks_truncated(r_text):
            s_title, s_text = _extract(rendered.html_scrolled, url)
            if len(s_text) > len(r_text):
                r_title, r_text, r_html = s_title, s_text, rendered.html_scrolled
        if _is_block_page(r_text) or _is_block_page(rendered.raw_text) or rendered.status in (401, 403, 429):
            blocked, r_text = True, ""
        else:
            raw_text = rendered.raw_text.strip()
        logger.info(f"ブラウザ取得での本文: {len(r_text)}文字")
        if len(r_text) > len(text):
            title, text, method, html = r_title or title, r_text, "browser", r_html
            final_url = rendered.final_url or final_url

    # ---- 複数ページ記事の結合
    pages = 1
    if text:
        text, pages = _follow_pages(html, final_url or url, text, use_browser=method == "browser")

    article = Article(url, title, text, method, pages=pages)
    status_note = "、".join(statuses)
    short = len(text) < min_chars
    paywall = _paywall_hint(html, text) if text else ""

    if _redirected_to_top(url, final_url):
        article.problem = PROBLEM_URL
        article.detail = f"トップページ（{final_url}）へ転送されました。URLの指定ミスか、記事が削除されています"
    elif text and _is_soft_404(title, text):
        article.problem = PROBLEM_URL
        article.detail = (f"「ページが見つかりません」「掲載終了」の画面が返っています（{status_note}、タイトル: {title[:40]}）。"
                          "URLの指定ミスか、記事が削除されています")
    elif short and static.status >= 500 and (rendered is None or rendered.status >= 500 or not rendered.status):
        article.text = ""
        article.problem = PROBLEM_NETWORK
        article.detail = (f"サイトがサーバーエラーを返しています（{status_note}）。URLの書式は正しく、"
                          "サイト側の一時的な障害の可能性があります")
    elif blocked and short:
        article.problem = PROBLEM_BLOCKED
        article.detail = (f"URLは存在しますが、サイト側にアクセスを拒否されました（{status_note}、ロボット確認など）。"
                          "URLの間違いではなく、自動取得が拒否されています")
    elif not text and static.error and (rendered is None or rendered.error or rendered.status >= 500):
        article.problem = PROBLEM_NETWORK
        reason = {"ssl": "サーバー証明書のエラー", "timeout": "タイムアウト"}.get(static.error, "接続エラー")
        article.detail = (f"サイトに接続できませんでした（{reason}、{status_note}）。"
                          "ホスト名は存在するのでURLの書式は正しく、サイト側の障害か通信の問題です")
    elif not text and (static.status >= 500 or (rendered is not None and rendered.status >= 500)):
        article.problem = PROBLEM_NETWORK
        article.detail = f"サイトがサーバーエラーを返しています（{status_note}）。一時的な障害の可能性があります"
    elif not text and len(raw_text) >= min_chars:
        article.text, article.method = raw_text, "browser"
        article.problem = PROBLEM_RAW
        article.detail = (f"本文の範囲を特定できなかったため、ページに表示されている全テキスト（{len(raw_text)}文字）で代用しています"
                          f"（{status_note}）。メニューや広告など記事と無関係な文が含まれます。取得ロジック側の限界です")
    elif not text:
        article.problem = PROBLEM_EMPTY
        article.detail = (f"ページは開けましたが記事本文を見つけられませんでした（{status_note}）。"
                          "URLは存在するので、動画・スライド・一覧ページなど記事形式でないURLか、取得ロジックが対応していないページです")
    elif _redirected_to_login(url, final_url):
        article.problem = PROBLEM_PARTIAL
        article.detail = f"ログイン・同意ページ（{final_url}）へ転送されました。ログインや利用確認が必要なページです"
    elif paywall:
        article.problem = PROBLEM_PARTIAL
        article.detail = (f"有料・会員限定の表示（「{paywall}」）があり、本文は途中までの可能性があります"
                          f"（取得できたのは{len(text)}文字）。URLは正しく開けています")
    elif short or _looks_truncated(text):
        article.problem = PROBLEM_PARTIAL
        reason = "本文が途中で切れています" if _looks_truncated(text) else f"本文が{min_chars}文字未満です"
        article.detail = (f"{reason}（{len(text)}文字、{status_note}）。URLは正しく開けているので、"
                          "ログイン・利用確認が必要なページか、もともと短い記事です")
    if article.problem:
        logger.warning(f"{article.detail}: {url}")
    return article


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--login":
        open_for_login(sys.argv[2])
        sys.exit(0)
    if len(sys.argv) != 2:
        print("usage: python src/article_extractor.py [--login] <URL>")
        sys.exit(2)
    article = fetch_article(sys.argv[1])
    if article.problem:
        print(f"[要確認: {article.problem}] {article.detail}\n")
    if article.text:
        print(f"[{article.method}] {article.title} ({len(article.text)}文字, {article.pages}ページ)\n")
        print(article.text)
    sys.exit(0 if article.ok else 1)
