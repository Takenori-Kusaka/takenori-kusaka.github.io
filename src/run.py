import logging
import yaml
import datetime
import glob
import os
import sys
from dotenv import load_dotenv
import anthropic
import requests
import json
import re
from logging.handlers import RotatingFileHandler

def setup_logger():
    """ロガーの設定"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # ログのフォーマット設定
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # コンソール出力用ハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイル出力用ハンドラ（ローテーション付き）
    log_file = 'src/run.log'
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

def load_environment():
    """環境変数の読み込みと検証"""
    logger.info("環境変数の読み込みを開始")
    load_dotenv()
    
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    
    if not ANTHROPIC_API_KEY or not PERPLEXITY_API_KEY:
        logger.error("必要なAPIキーが設定されていません")
        sys.exit(1)
        
    logger.info("環境変数の読み込みが完了")
    return ANTHROPIC_API_KEY, PERPLEXITY_API_KEY

def get_article_info(url, api_key):
    """Perplexity APIを使用して記事の情報を取得"""
    logger.info(f"記事情報の取得開始: {url}")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": """記事の内容を要約してください。以下の点に注意してください：
                - ポッドキャストで扱う記事なので、要約は300文字以上700文字以内に収めてください
                - [1]や[2]などの引用符は含めないでください
                - 文末に出典を示す必要はありません"""
            },
            {
                "role": "user",
                "content": f"次のURLの記事を要約してください: {url}"
            }
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 1000,
        "return_images": False,
        "return_related_questions": False,
        "search_domain_filter": ["sorae.info"],
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 1
    }
    
    try:
        session = requests.Session()
        response = session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        # レスポンスヘッダーとステータスコードのログ
        logger.debug(f"レスポンスヘッダー: {dict(response.headers)}")
        logger.debug(f"ステータスコード: {response.status_code}")
        
        response.raise_for_status()
        
        try:
            result = response.json()
            logger.debug(f"APIレスポンス: {result}")
            
            content = result["choices"][0]["message"]["content"]
            logger.info(f"記事情報の取得成功: {url}")
            logger.debug(f"取得した要約: {content[:100]}...")
            return content
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"APIレスポンスの解析エラー: {str(e)}")
            logger.debug(f"受信したレスポンス: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Perplexity API エラー: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"詳細エラー: {e.response.text}")
            logger.debug(f"ステータスコード: {e.response.status_code}")
            logger.debug(f"レスポンスヘッダー: {dict(e.response.headers)}")
        return None

def extract_text_from_message(message):
    """Anthropicのレスポンスからテキストを抽出"""
    if isinstance(message, list):
        # リストの場合は最初の要素のtextを取得
        return message[0].text if message and hasattr(message[0], 'text') else None
    elif hasattr(message, 'text'):
        # 単一のオブジェクトの場合
        return message.text
    else:
        # その他の場合は文字列として扱う
        return str(message)

def generate_headline(content, client):
    """Claude APIを使用して見出しを生成"""
    logger.info("見出し生成開始")
    logger.debug(f"要約内容: {content[:100]}...")
    
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            temperature=0,
            system="以下のルールに従って見出しを作成してください：\n- 10〜20文字で簡潔に\n- 「」で囲む\n- 説明や理由を含めない\n- 一行のみ",
            messages=[{
                "role": "user",
                "content": f"次の記事内容から見出しを作成してください：\n\n{content}"
            }]
        )
        
        result = extract_text_from_message(message.content)
        if not result:
            logger.error("見出しの生成に失敗しました")
            return None
        
        # 引用符で囲まれた部分を抽出
        match = re.search(r'「(.+?)」|"(.+?)"', result)
        if match:
            headline = match.group(1) or match.group(2)
        else:
            headline = result.strip()
            
        logger.info(f"見出し生成成功: {headline}")
        return headline
    except Exception as e:
        logger.error(f"Claude API エラー: {str(e)}")
        return None

def determine_main_topic(headlines, client):
    """最も重要なトピックを決定"""
    logger.info("メインタイトル生成開始")
    logger.debug(f"見出しリスト: {headlines}")
    
    prompt = "以下の記事の見出しの中から最も重要なものを選び、タイトルを作成してください。"
    prompt += "タイトルは以下のルールに従ってください：\n"
    prompt += "- 10〜20文字で簡潔に\n"
    prompt += "- 「」で囲む\n"
    prompt += "- 説明や理由を含めない\n"
    prompt += "- 一行のみ\n"
    prompt += "- 「を選びます」「にしました」などの余分な説明は含めない\n\n"
    prompt += "提示された見出し：\n"
    for i, headline in enumerate(headlines, 1):
        prompt += f"{i}. {headline}\n"

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            temperature=0,
            system="新聞の見出し作成の専門家として、提示された見出しの中から最も重要なものを選び、全体を表す見出しを作成してください。",
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        result = extract_text_from_message(message.content)
        if not result:
            logger.error("メインタイトルの生成に失敗しました")
            return None
            
        # 引用符で囲まれた部分を抽出
        match = re.search(r'「(.+?)」|"(.+?)"', result)
        if match:
            title = match.group(1) or match.group(2)
        else:
            title = result.split('\n')[0].strip()
            
        logger.info(f"メインタイトル生成成功: {title}")
        return title
    except Exception as e:
        logger.error(f"Claude API エラー: {str(e)}")
        return None

def generate_slide(date, headlines, main_title):
    """スライドショーのMarkdownを生成"""
    logger.info("スライド生成開始")
    
    HEADER = """---
marp: true
theme: myformat
paginate: true
---

"""
    PAGE_TEMPLATE = """<!--
_class: normal
-->

![bg](./stringarea.png)
# {}

"""

    result = HEADER
    for index, current_headline in enumerate(headlines, 1):
        page = PAGE_TEMPLATE.format(main_title)
        for i, headline in enumerate(headlines, 1):
            if i == index:
                page += f"## {i:02d}. {headline}\n"
            else:
                page += f"### {i:02d}. {headline}\n"
        if index < len(headlines):  # 最後のページ以外は改ページを追加
            page += "---\n"
        result += page

    filename = date.strftime('%Y-%m-%d') + '-topic.md'
    filepath = './doc/' + filename
    logger.info(f"スライドファイル生成: {filepath}")
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)
        logger.info("スライド生成完了")
    except IOError as e:
        logger.error(f"ファイル書き込みエラー: {str(e)}")
        raise

def generate_post(date, headlines, summaries, main_title):
    """ブログ投稿用のMarkdownを生成"""
    logger.info("ブログ投稿生成開始")
    
    try:
        gl = glob.glob('./_posts/*.md')
        allposts = list(gl)
        allposts.sort()
        latest_post = allposts[-1].replace('.md', '').split('-')
        latest_num = int(latest_post[-1])
        latest_date = '{}-{}-{}'.format(latest_post[-4].split('\\')[-1], latest_post[-3], latest_post[-2])
        if latest_date == date.strftime('%Y-%m-%d'):
            logger.info("同日の投稿が存在します")
        else:
            latest_num = latest_num + 1
            logger.info(f"新規投稿番号: {latest_num}")

        filename = date.strftime('%Y-%m-%d') + '-{}.md'.format(latest_num)
        HEADER = """---
actor_ids:
- kokorokagami
- touden
audio_file_path: /audio/{0}
audio_file_size: 0
date: {1} 20:00:00 +0900
description: kokorokagamiとtoudenの2人で、{2}{3} について話しました。
duration: "00:00"
layout: article
title: {4}. {5} {6}
---

以下のようなトピックについて話をしました。

""".format(
            date.strftime('%Y%m%d') + 'm.mp3',
            date.strftime('%Y-%m-%d'),
            headlines[0],
            "、{} など".format(headlines[1]) if len(headlines) > 1 else "",
            latest_num,
            date.strftime('%Y/%m/%d'),
            main_title
        )

        FOOTER = """
___

本ラジオはあくまで個人の見解であり現実のいかなる団体を代表するものではありません  
ご理解頂ますようよろしくおねがいします  
"""

        result = HEADER
        for i, (headline, summary) in enumerate(zip(headlines, summaries), 1):
            result += f"## {i:02d}. {headline}\n\n{summary}\n\n"

        result += FOOTER
        filepath = './_posts/' + filename
        logger.info(f"ブログ投稿ファイル生成: {filepath}")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)
        logger.info("ブログ投稿生成完了")
    except Exception as e:
        logger.error(f"ブログ投稿生成エラー: {str(e)}")
        raise

def main():
    """メイン処理"""
    logger.info("プログラム実行開始")
    try:
        # APIキーの読み込み
        ANTHROPIC_API_KEY, PERPLEXITY_API_KEY = load_environment()
        
        # Anthropic APIクライアントの初期化
        anthropic_client = anthropic.Client(api_key=ANTHROPIC_API_KEY)
        
        # topic.yamlの読み込み
        try:
            with open('src/topic.yaml', 'r', encoding='utf-8') as f:
                topics = yaml.safe_load(f)
                if not topics or 'Topic' not in topics or 'Date' not in topics:
                    raise ValueError("topic.yamlの形式が不正です")
                if not isinstance(topics['Date'], datetime.date):
                    topics['Date'] = datetime.datetime.strptime(topics['Date'], '%Y-%m-%d').date()
                if not isinstance(topics['Topic'], list) or not topics['Topic']:
                    raise ValueError("Topicは1つ以上のURLを含む配列である必要があります")
            logger.info(f"topic.yaml読み込み完了: {len(topics['Topic'])}件のトピック")
        except Exception as e:
            logger.error(f"topic.yaml読み込みエラー: {str(e)}")
            raise

        # 各URLから記事情報を取得
        summaries = []
        headlines = []
        for url in topics['Topic']:
            logger.info(f"URL処理開始: {url}")
            summary = get_article_info(url, PERPLEXITY_API_KEY)
            if summary:
                summaries.append(summary)
                headline = generate_headline(summary, anthropic_client)
                if headline:
                    headlines.append(headline)
                else:
                    logger.error(f"見出し生成失敗: {url}")
                    raise Exception("見出し生成に失敗しました")
            else:
                logger.error(f"記事情報取得失敗: {url}")
                raise Exception("記事情報の取得に失敗しました")

        # メインタイトルを生成
        main_title = determine_main_topic(headlines, anthropic_client)
        if not main_title:
            logger.error("メインタイトル生成失敗")
            raise Exception("メインタイトルの生成に失敗しました")

        # ファイルを生成
        generate_slide(topics['Date'], headlines, main_title)
        generate_post(topics['Date'], headlines, summaries, main_title)
        
        logger.info("プログラム実行完了")
        
    except Exception as e:
        logger.error(f"プログラム実行エラー: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
