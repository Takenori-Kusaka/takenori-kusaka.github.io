import logging
import yaml
import datetime
import sys
import traceback  # tracebackモジュールを追加

from logger_config import LoggerConfig
from environment_manager import EnvironmentManager
from article_fetcher import ArticleFetcher
from run_cache import RunCache
from headline_generator import HeadlineGenerator
from content_generator import ContentGenerator

logger = LoggerConfig.setup_logger()

class PodcastContentApp:
    def __init__(self):
        self.env_manager = EnvironmentManager()
        self.content_generator = None

    def load_topic_yaml(self, path='src/topic.yaml'):
        """topic.yamlの読み込み

        書式（URLを並べるだけでよい）:
            date: 2026-11-15
            topics:
              - https://example.com/article            # URLだけ
              - url: [https://a.example/1, https://b.example/2]   # 同じ話題の複数ソースを1トピックにまとめる
              - text: |                                # URLなしで本文を直接書く
                  本文...
        旧書式（Date / Topic / link / text）もそのまま読める。
        戻り値は {'Date': date, 'Topic': [{'urls': [...], 'text': str}, ...]}。
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                raise ValueError("topic.yamlの形式が不正です（date と topics が必要です）")
            raw = {str(k).lower(): v for k, v in raw.items()}

            date = raw.get('date') or datetime.date.today()
            if isinstance(date, datetime.datetime):
                date = date.date()
            elif not isinstance(date, datetime.date):
                date = datetime.datetime.strptime(str(date), '%Y-%m-%d').date()

            items = raw.get('topics') or raw.get('topic')
            if not isinstance(items, list) or not items:
                raise ValueError("topics は1つ以上のアイテムを含む配列である必要があります")

            topics = []
            for index, item in enumerate(items, 1):
                if isinstance(item, str):
                    item = {'url': item}
                if not isinstance(item, dict):
                    raise ValueError(f"{index}番目のトピックの書き方が不正です（URLの文字列か、url / text を持つ項目にしてください）")
                item = {str(k).lower(): v for k, v in item.items()}
                unknown = set(item) - {'url', 'urls', 'link', 'text'}
                if unknown:
                    raise ValueError(f"{index}番目のトピックに未知のキーがあります: {', '.join(sorted(unknown))}（使えるのは url / text）")
                urls = item.get('url') or item.get('urls') or item.get('link') or []
                if isinstance(urls, str):
                    urls = [urls]
                if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
                    raise ValueError(f"{index}番目のトピックの url は文字列か、文字列の配列で指定してください")
                urls = [u.strip() for u in urls if u.strip()]
                text = str(item.get('text') or '').strip()
                if not urls and not text:
                    raise ValueError(f"{index}番目のトピックに url も text もありません")
                topics.append({'urls': urls, 'text': text})

            all_urls = [u for t in topics for u in t['urls']]
            for u in sorted({u for u in all_urls if all_urls.count(u) > 1}):
                logger.warning(f"同じURLが複数回指定されています: {u}")
            logger.info(f"topic.yaml読み込み完了: {date} / {len(topics)}件のトピック")
            return {'Date': date, 'Topic': topics}
        except Exception as e:
            logger.error(f"topic.yaml読み込みエラー: {str(e)}")
            raise

    def run(self):
        """メイン処理"""
        logger.info("プログラム実行開始")
        try:
            # 環境変数の読み込み
            anthropic_api_key = self.env_manager.load_environment()

            # APIクライアントの初期化
            # 途中経過のキャッシュ（--no-cache で無効化して全て取り直す）
            cache = RunCache(enabled='--no-cache' not in sys.argv)
            article_fetcher = ArticleFetcher(anthropic_api_key, cache)
            headline_generator = HeadlineGenerator(anthropic_api_key)
            self.content_generator = ContentGenerator()

            # topic.yamlの読み込み
            topics = self.load_topic_yaml()

            # 各トピックから記事情報を取得
            summaries = []
            youtube_summaries = []
            headlines = []
            slide_points = []
            for topic in topics['Topic']:
                link = topic['urls']
                text = topic['text']
                logger.info(f"トピック処理開始: {', '.join(link) or '(テキストのみ)'}")
                # 途中で失敗して再実行したとき、完了済みのトピックは作り直さない
                key = RunCache.key("topic", *link, text)

                def cached(name, produce):
                    value = cache.get(key, name)
                    if value is not None:
                        logger.info(f"前回の結果を再利用します（キャッシュ: {name}）")
                        return value
                    value = produce()
                    if value:
                        cache.set(key, name, value)
                    return value

                # textが空ならURLのページから本文を自動取得する（textがあればそれを優先）
                summary = cached("summary", lambda: article_fetcher.get_article_info(link, text))
                if not summary:
                    logger.error(f"記事情報取得失敗: {link}")
                    raise Exception("記事情報の取得に失敗しました")
                youtube_summary = cached("youtube_summary", lambda: article_fetcher.get_youtube_summary(summary))
                if not youtube_summary:
                    logger.error(f"YouTube用要約生成失敗: {link}")
                    raise Exception("YouTube用要約の生成に失敗しました")
                headline = cached("headline", lambda: headline_generator.generate_headline(summary))
                if not headline:
                    logger.error(f"見出し生成失敗: {link}")
                    raise Exception("見出し生成に失敗しました")
                summaries.append(summary)
                youtube_summaries.append(youtube_summary)
                headlines.append(headline)
                slide_points.append(cached("slide_points", lambda: article_fetcher.generate_slide_points(headline, summary)))

            # メインタイトルを生成
            main_title = headline_generator.determine_main_topic(headlines)
            if not main_title:
                logger.error("メインタイトル生成失敗")
                raise Exception("メインタイトルの生成に失敗しました")

            # 最新の投稿番号を取得
            latest_num = self.content_generator.get_latest_post_number(topics['Date'])

            # ファイルを生成
            self.content_generator.generate_slide(topics['Date'], headlines, summaries, slide_points)
            self.content_generator.generate_post(topics['Date'], headlines, summaries, main_title, latest_num)
            youtube_description = self.content_generator.generate_youtube_description(topics['Date'], headlines, youtube_summaries, main_title, latest_num)
            self.content_generator.save_youtube_description(topics['Date'], youtube_description)

            for warning in article_fetcher.warnings:
                logger.warning(f"要確認（全文ではない可能性）: {warning}")

            logger.info("プログラム実行完了")

        except Exception as e:
            logger.error(f"プログラム実行エラー: {str(e)}")
            logger.error(f"詳細なエラー情報: {traceback.format_exc()}")  # スタックトレースをログに出力
            sys.exit(1)

if __name__ == "__main__":
    app = PodcastContentApp()
    app.run()
