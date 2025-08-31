import requests
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

class ArticleFetcher:
    def __init__(self, perplexity_api_key, anthropic_api_key):
        self.perplexity_api_key = perplexity_api_key
        self.anthropic_api_key = anthropic_api_key
        self.perplexity_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {perplexity_api_key}",
            "Content-Type": "application/json"
        }
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

    def get_article_info(self, link, text=""):
        """Perplexity APIを使用して記事の情報を取得、またはテキストを処理"""
        if link:
            logger.info(f"記事情報の取得開始: {link}")
            
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
                        "content": f"次のURLの記事を要約してください: {link}"
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
                    headers=self.perplexity_headers,
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
                    logger.info(f"記事情報の取得成功: {link}")
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
        elif text:
            logger.info("テキストの処理開始")
            return self.summarize_text(text)
        else:
            logger.error("リンクもテキストも提供されていません")
            return None

    def summarize_text(self, text):
        """Anthropicのモデル（Claude）を使用してテキストを要約"""
        logger.info("テキストの要約開始")
        
        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                temperature=0.2,
                system="あなたは与えられた文章を300文字以上700文字以内に要約する専門家です。重要なポイントを保持しつつ、簡潔で魅力的な要約を作成してください。",
                messages=[
                    {
                        "role": "user",
                        "content": f"以下の文章を要約してください：\n\n{text}"
                    }
                ]
            )
            
            summary = message.content[0].text
            
            logger.info(f"テキストの要約成功（{len(summary)}文字）")
            logger.debug(f"生成された要約: {summary[:100]}...")
            return summary
        except Exception as e:
            logger.error(f"Anthropic API エラー: {str(e)}")
            return None

    def get_youtube_summary(self, summary):
        """Anthropicのモデル（Claude）を使用して、要約を140文字以内に再要約"""
        logger.info("YouTube用の短い要約の生成開始")
        
        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                temperature=0.2,
                system="あなたは与えられた文章を140文字以内に要約する専門家です。重要なポイントを保持しつつ、簡潔で魅力的な要約を作成してください。",
                messages=[
                    {
                        "role": "user",
                        "content": f"以下の文章を140文字以内に要約してください：\n\n{summary}"
                    }
                ]
            )
            
            short_summary = message.content[0].text
            
            if len(short_summary) > 140:
                short_summary = short_summary[:137] + "..."
            
            logger.info(f"YouTube用の短い要約の生成成功（{len(short_summary)}文字）")
            logger.debug(f"生成された短い要約: {short_summary}")
            return short_summary
        except Exception as e:
            logger.error(f"Anthropic API エラー: {str(e)}")
            return None
