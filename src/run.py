import logging
import yaml
import datetime
import sys

from logger_config import LoggerConfig
from environment_manager import EnvironmentManager
from article_fetcher import ArticleFetcher
from headline_generator import HeadlineGenerator
from content_generator import ContentGenerator

logger = LoggerConfig.setup_logger()

class PodcastContentApp:
    def __init__(self):
        self.env_manager = EnvironmentManager()
        self.content_generator = None

    def load_topic_yaml(self):
        """topic.yamlの読み込み"""
        try:
            with open('src/topic.yaml', 'r', encoding='utf-8') as f:
                topics = yaml.safe_load(f)
                if not topics or 'Topic' not in topics or 'Date' not in topics:
                    raise ValueError("topic.yamlの形式が不正です")
                if not isinstance(topics['Date'], datetime.date):
                    topics['Date'] = datetime.datetime.strptime(topics['Date'], '%Y-%m-%d').date()
                if not isinstance(topics['Topic'], list) or not topics['Topic']:
                    raise ValueError("Topicは1つ以上のアイテムを含む配列である必要があります")
                for item in topics['Topic']:
                    if not isinstance(item, dict) or 'link' not in item or 'text' not in item:
                        raise ValueError("各Topicアイテムは'link'と'text'キーを持つ辞書である必要があります")
                logger.info(f"topic.yaml読み込み完了: {len(topics['Topic'])}件のトピック")
                return topics
        except Exception as e:
            logger.error(f"topic.yaml読み込みエラー: {str(e)}")
            raise

    def run(self):
        """メイン処理"""
        logger.info("プログラム実行開始")
        try:
            # 環境変数の読み込み
            anthropic_api_key, perplexity_api_key = self.env_manager.load_environment()

            # APIクライアントの初期化
            article_fetcher = ArticleFetcher(perplexity_api_key, anthropic_api_key)
            headline_generator = HeadlineGenerator(anthropic_api_key)
            self.content_generator = ContentGenerator()

            # topic.yamlの読み込み
            topics = self.load_topic_yaml()

            # 各トピックから記事情報を取得
            summaries = []
            youtube_summaries = []
            headlines = []
            for topic in topics['Topic']:
                link = topic['link']
                text = topic['text']
                logger.info(f"トピック処理開始: {link}")
                summary = article_fetcher.get_article_info(link, text)
                if summary:
                    summaries.append(summary)
                    youtube_summary = article_fetcher.get_youtube_summary(summary)
                    if youtube_summary:
                        youtube_summaries.append(youtube_summary)
                    else:
                        logger.error(f"YouTube用要約生成失敗: {link}")
                        raise Exception("YouTube用要約の生成に失敗しました")
                    headline = headline_generator.generate_headline(summary)
                    if headline:
                        headlines.append(headline)
                    else:
                        logger.error(f"見出し生成失敗: {link}")
                        raise Exception("見出し生成に失敗しました")
                else:
                    logger.error(f"記事情報取得失敗: {link}")
                    raise Exception("記事情報の取得に失敗しました")

            # メインタイトルを生成
            main_title = headline_generator.determine_main_topic(headlines)
            if not main_title:
                logger.error("メインタイトル生成失敗")
                raise Exception("メインタイトルの生成に失敗しました")

            # 最新の投稿番号を取得
            latest_num = self.content_generator.get_latest_post_number(topics['Date'])

            # ファイルを生成
            self.content_generator.generate_slide(topics['Date'], headlines, summaries)
            self.content_generator.generate_post(topics['Date'], headlines, summaries, main_title, latest_num)
            youtube_description = self.content_generator.generate_youtube_description(topics['Date'], headlines, youtube_summaries, main_title, latest_num)
            self.content_generator.save_youtube_description(topics['Date'], youtube_description)

            logger.info("プログラム実行完了")

        except Exception as e:
            logger.error(f"プログラム実行エラー: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    app = PodcastContentApp()
    app.run()
