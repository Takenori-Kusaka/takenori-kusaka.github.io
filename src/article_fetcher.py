import dataclasses
import logging
import re
import subprocess
import sys
import webbrowser
import anthropic

from article_extractor import (
    PROBLEM_EMPTY, PROBLEM_PARTIAL, PROBLEM_RAW, PROBLEM_URL,
    Article, fetch_article, open_for_login,
)
from run_cache import RunCache

logger = logging.getLogger(__name__)

class ArticleFetcher:
    # 要約に渡す本文の上限（極端に長いページでのコストと失敗を避ける）
    MAX_BODY_CHARS = 40000
    # 自動取得したページに記事本文が無いとき、要約の代わりにモデルに返させる目印
    NO_ARTICLE_PREFIX = "取得失敗"
    # 貼り付けられた本文として受け付ける最小の長さ（誤操作で空のまま進むのを防ぐ）
    MIN_PASTED_CHARS = 30

    def __init__(self, anthropic_api_key, cache=None):
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.cache = cache or RunCache(enabled=False)
        # 全文を取れないまま進めた記事（実行の最後にまとめて知らせる）
        self.warnings = []
        # コンソールで利用者に判断を尋ねられるか
        self.interactive = sys.stdin.isatty()

    def get_article_info(self, link, text=""):
        """記事の要約を取得する。

        topic.yamlのtextに本文が貼られていればそれを要約する（手動指定を最優先）。
        空ならlinkのページから本文を自動抽出して要約する。自動取得で全文を得られない場合は
        中断せず、コンソールで対応（ログイン／手動コピー＆貼り付け／見える範囲で続行）を選んでもらう。
        """
        links = [link] if isinstance(link, str) else list(link or [])
        links = [l.strip() for l in links if l and l.strip()]
        text = (text or "").strip()

        if text:
            logger.info("topic.yamlのテキストを要約します")
            return self.summarize_text(text)

        if not links:
            logger.error("リンクもテキストも提供されていません")
            return None

        if len(links) > 1:
            return self.summarize_sources(links)

        link = links[0]
        article = self.get_article(link)
        while article is not None:
            logger.info(f"記事本文の取得成功（{article.method}, {len(article.text)}文字）: {article.title}")
            body = f"タイトル：{article.title}\n\n{article.text}" if article.title else article.text
            # 人が貼り付けた本文は信頼し、「記事本文が無い」判定は自動取得分にだけ行う
            summary = self.summarize_text(body, fetched=article.method != "manual")
            if not (summary and summary.startswith(self.NO_ARTICLE_PREFIX)):
                return summary
            # 取得はできたが中身が記事ではなかった（一覧・動画ページ・無関係な文章など）
            article.problem = PROBLEM_EMPTY
            article.detail = (f"ページから文章は取れましたが、記事本文ではありませんでした（AIの判定: {summary}）。"
                              "URLは開けているので、URLが記事ページを指していないか、取得ロジックが本文を外しています")
            if not self.interactive:
                logger.error(f"{article.detail}: {link}")
                return None
            article = self.resolve_problem(article)
            self._save_article(link, article)
        return None

    def summarize_sources(self, links):
        """同じ話題を扱う複数のURLを、1つのトピックとしてまとめて要約する"""
        per_source = self.MAX_BODY_CHARS // len(links)
        parts = []
        for index, link in enumerate(links, 1):
            article = self.get_article(link)
            if article is None:
                return None
            logger.info(f"記事本文の取得成功（{article.method}, {len(article.text)}文字）: {article.title}")
            if len(article.text) > per_source:
                logger.warning(f"資料{index}が長いため先頭{per_source}文字に切り詰めます（元: {len(article.text)}文字）")
            parts.append(f"【資料{index}】{article.title}\n{article.text[:per_source]}")
        note = f"次の{len(links)}件は同じ話題を扱う資料です。重複をまとめ、1つの記事として要約してください。\n\n"
        return self.summarize_text(note + "\n\n".join(parts))

    def get_article(self, link):
        """記事本文を得る（キャッシュ→自動取得→必要なら利用者に確認）。中止なら None"""
        key = RunCache.key("article", link)
        cached = self.cache.get(key, "article")
        if cached:
            logger.info(f"前回取得した記事本文を再利用します（キャッシュ）: {link}")
            return Article(**cached)
        logger.info(f"記事本文の取得開始: {link}")
        article = self.resolve_problem(fetch_article(link))
        self._save_article(link, article)
        return article

    def _save_article(self, link, article):
        if article is not None:
            self.cache.set(RunCache.key("article", link), "article", dataclasses.asdict(article))

    def resolve_problem(self, article):
        """取得結果に問題があれば原因を表示し、どうするかをコンソールで選んでもらう。

        使ってよい Article を返す。中止する場合は None。
        """
        while article.problem:
            is_url_problem = article.problem == PROBLEM_URL
            can_use_visible = bool(article.text) and article.problem in (PROBLEM_PARTIAL, PROBLEM_RAW)

            if not self.interactive:
                # 対話できない環境では勝手に判断できない。見えている範囲がある場合のみ警告付きで続行
                if not can_use_visible:
                    kind = "URLの指定ミスの可能性" if is_url_problem else "取得側の問題"
                    logger.error(f"{kind}: {article.detail}: {article.url}")
                    return None
                logger.warning("対話できない実行環境のため、見えている範囲で続行します")
                self.warnings.append(f"{article.url}: {article.detail}")
                break

            print("\n" + "=" * 72)
            print(f"記事を十分に取得できませんでした: {article.url}")
            print(f"切り分け: {'【URLの指定ミスの可能性】' if is_url_problem else '【URLは正しく、取得側の問題】'}")
            print(f"  {article.detail}")
            if article.text:
                preview = " ".join(article.text[:200].split())
                print(f"取得できた範囲（{len(article.text)}文字）: {preview}{'…' if len(article.text) > 200 else ''}")
            print("どうしますか？")
            if not is_url_problem:
                print("  1. ログイン／利用確認をすれば全文が読める → 専用ブラウザを開くので操作してください（セッションを保存して自動で取り直します）")
            print("  2. 自分のブラウザで開いて本文をコピーし、貼り付ける")
            if can_use_visible:
                print("  3. アカウントやライセンスがない／これで全文 → 見えている範囲で進める")
            print("  4. もう一度自動取得を試す")
            print("  5. URLを入力し直す")
            print("  6. 中止する")
            choice = input("番号を入力してください: ").strip()
            if choice == "1" and not is_url_problem:
                try:
                    open_for_login(article.url)
                except Exception as e:
                    print(f"専用ブラウザを開けませんでした: {e}")
                    continue
                article = fetch_article(article.url)
            elif choice == "2":
                pasted = self.read_pasted_text(article.url)
                if pasted:
                    return Article(article.url, article.title, pasted, "manual")
            elif choice == "3" and can_use_visible:
                self.warnings.append(f"{article.url}: 見えている範囲で作成（{len(article.text)}文字）")
                break
            elif choice == "4":
                article = fetch_article(article.url)
            elif choice == "5":
                new_url = input("正しいURL: ").strip()
                if new_url:
                    article = fetch_article(new_url)
            elif choice == "6":
                logger.error(f"利用者の判断で中止しました: {article.url}")
                return None
        article.problem, article.detail = "", ""
        return article

    def read_pasted_text(self, url):
        """利用者のブラウザでURLを開き、コピーしてもらった本文を受け取る"""
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(f"ブラウザで開きました: {url}")
        print("記事本文を選択してコピーしたら、次のどちらかで渡してください。")
        print("  ・何も入力せず Enter → クリップボードの内容を読み取ります")
        print("  ・ここに貼り付けて、最後に END とだけ書いた行を入力して Enter")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "END":
                break
            if not lines and not line.strip():
                # 貼り付けの先頭が空行だった場合も、クリップボードに同じ内容があるので問題ない
                lines = self.read_clipboard().splitlines()
                break
            lines.append(line)
        text = "\n".join(lines).strip()
        if len(text) < self.MIN_PASTED_CHARS:
            print(f"受け取った本文が短すぎます（{len(text)}文字）。もう一度選んでください。")
            return ""
        print(f"本文を受け取りました（{len(text)}文字）。")
        return text

    @staticmethod
    def read_clipboard():
        try:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            try:
                return root.clipboard_get()
            finally:
                root.destroy()
        except Exception:
            pass
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                capture_output=True, timeout=15,
            )
            return out.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"クリップボードを読めませんでした: {e}")
            return ""

    def summarize_text(self, text, fetched=False):
        """Anthropicのモデル（Claude）を使用してテキストを要約

        fetched=True は自動取得したページのテキスト。記事本文が含まれない場合は
        NO_ARTICLE_PREFIX で始まる1行が返る。
        """
        guard = (
            f"\n- 入力に記事本文が含まれていない場合（ロボット確認やアクセス拒否の画面、ログイン・会員登録の要求、"
            f"メニューや記事一覧だけ、タイトルと無関係な文章だけ等）は、要約せず「{self.NO_ARTICLE_PREFIX}：」で始まる1行で理由だけを書く"
            if fetched else ""
        )
        logger.info("テキストの要約開始")
        if len(text) > self.MAX_BODY_CHARS:
            logger.warning(f"本文が長いため先頭{self.MAX_BODY_CHARS}文字に切り詰めます（元: {len(text)}文字）")
            text = text[:self.MAX_BODY_CHARS]

        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-5-5",
                max_tokens=4000,
                system=(
                    "あなたはポッドキャストで扱う記事を要約する専門家です。与えられた記事本文を300文字以上700文字以内の日本語で要約してください。\n"
                    "- 重要なポイント（何が起きたか、数値や固有名詞、意義）を保持する\n"
                    "- 入力はWebページから取り出したテキストで、広告、メニュー、関連記事の見出し、SNS共有ボタン、著者プロフィール、コメントなど記事本文ではない断片が混ざることがある。それらは無視し、記事本文だけを要約する\n"
                    "- 出力はMarkdown記法を使わないプレーンテキストの文章のみ（見出し、箇条書き、太字、表は禁止）\n"
                    "- 冒頭にタイトルや前置きを付けず、本文から書き始める\n"
                    "- 入力に書かれていない内容は補わない。元の本文が短い場合は300文字に満たなくてよい\n"
                    "- [1]などの引用番号や出典は含めない"
                    + guard
                ),
                messages=[
                    {
                        "role": "user",
                        "content": f"以下の文章を要約してください：\n\n{text}"
                    }
                ]
            )

            summary = next((b.text for b in message.content if b.type == "text"), None)
            if summary is None:
                raise ValueError("レスポンスにtextブロックがありません")
            summary = self.strip_markdown(summary)

            logger.info(f"テキストの要約成功（{len(summary)}文字）")
            logger.debug(f"生成された要約: {summary[:100]}...")
            return summary
        except Exception as e:
            logger.error(f"Anthropic API エラー: {str(e)}")
            return None

    @staticmethod
    def strip_markdown(text):
        """見出し・箇条書き・太字などのMarkdown記法と引用番号を除去して平文にする"""
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'(\*\*|__)(.+?)\1', r'\2', text)
        text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
        return re.sub(r'\n{3,}', '\n\n', text).strip()

    def generate_slide_points(self, headline, summary, count=3, max_chars=45):
        """スライド用の短い箇条書きをClaudeで生成する（失敗時はNone）"""
        logger.info("スライド用箇条書きの生成開始")
        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-5-5",
                max_tokens=4000,
                system=(
                    "あなたはポッドキャスト用スライドの編集者です。記事要約から、スライドに載せる箇条書きを作成します。\n"
                    f"- ちょうど{count}項目、各項目は全角{max_chars}文字以内の体言止めまたは短い一文\n"
                    "- 各項目は単独で意味が通じ、数値・固有名詞などの重要な事実を含める\n"
                    "- 各項目は異なる観点（何が起きたか／詳細・数値／意義や今後）にする\n"
                    "- 見出しと重複する内容は避ける\n"
                    "- 出力は「- 」で始まる行のみ。前置き、見出し、太字、番号、句点は禁止"
                ),
                messages=[{
                    "role": "user",
                    "content": f"見出し：{headline}\n\n要約：\n{summary}"
                }]
            )
            raw = next((b.text for b in message.content if b.type == "text"), "")
            points = []
            for line in raw.splitlines():
                line = re.sub(r'^\s*[-*・]\s*', '', line).strip().rstrip('。')
                line = self.strip_markdown(line)
                if len(line) >= 3:
                    points.append(line)
            points = points[:count]
            if not points:
                return None
            logger.info(f"スライド用箇条書きの生成成功（{len(points)}項目）")
            return points
        except Exception as e:
            logger.error(f"スライド用箇条書き生成エラー: {str(e)}")
            return None

    def get_youtube_summary(self, summary):
        """Anthropicのモデル（Claude）を使用して、要約を140文字以内に再要約"""
        logger.info("YouTube用の短い要約の生成開始")
        
        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-5-5",
                max_tokens=4000,
                system="あなたは与えられた文章を140文字以内に要約する専門家です。重要なポイントを保持しつつ、簡潔で魅力的な要約を作成してください。",
                messages=[
                    {
                        "role": "user",
                        "content": f"以下の文章を140文字以内に要約してください：\n\n{summary}"
                    }
                ]
            )
            
            short_summary = next((b.text for b in message.content if b.type == "text"), None)
            if short_summary is None:
                raise ValueError("レスポンスにtextブロックがありません")
            
            if len(short_summary) > 140:
                short_summary = short_summary[:137] + "..."
            
            logger.info(f"YouTube用の短い要約の生成成功（{len(short_summary)}文字）")
            logger.debug(f"生成された短い要約: {short_summary}")
            return short_summary
        except Exception as e:
            logger.error(f"Anthropic API エラー: {str(e)}")
            return None
