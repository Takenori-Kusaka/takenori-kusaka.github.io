import requests
import json
import logging

logger = logging.getLogger(__name__)

class ArticleFetcher:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def get_article_info(self, url):
        """Perplexity APIを使用して記事の情報を取得"""
        logger.info(f"記事情報の取得開始: {url}")
        
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
                headers=self.headers,
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