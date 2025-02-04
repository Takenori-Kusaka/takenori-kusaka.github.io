import re
import logging
import anthropic

logger = logging.getLogger(__name__)

class HeadlineGenerator:
    def __init__(self, api_key):
        self.client = anthropic.Client(api_key=api_key)

    @staticmethod
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

    def generate_headline(self, content):
        """Claude APIを使用して見出しを生成"""
        logger.info("見出し生成開始")
        logger.debug(f"要約内容: {content[:100]}...")
        
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=100,
                temperature=0,
                system="以下のルールに従って見出しを作成してください：\n- 10〜20文字で簡潔に\n- 「」で囲む\n- 説明や理由を含めない\n- 一行のみ",
                messages=[{
                    "role": "user",
                    "content": f"次の記事内容から見出しを作成してください：\n\n{content}"
                }]
            )
            
            result = self.extract_text_from_message(message.content)
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

    def determine_main_topic(self, headlines):
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
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                temperature=0,
                system="新聞の見出し作成の専門家として、提示された見出しの中から最も重要なものを選び、全体を表す見出しを作成してください。",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            result = self.extract_text_from_message(message.content)
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