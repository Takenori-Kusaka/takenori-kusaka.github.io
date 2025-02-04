import os
import sys
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class EnvironmentManager:
    def __init__(self):
        self.anthropic_api_key = None
        self.perplexity_api_key = None

    def load_environment(self):
        """環境変数の読み込みと検証"""
        logger.info("環境変数の読み込みを開始")
        load_dotenv()
        
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        
        if not self.anthropic_api_key or not self.perplexity_api_key:
            logger.error("必要なAPIキーが設定されていません")
            sys.exit(1)
            
        logger.info("環境変数の読み込みが完了")
        return self.anthropic_api_key, self.perplexity_api_key

    @property
    def api_keys(self):
        """APIキーを取得"""
        if not self.anthropic_api_key or not self.perplexity_api_key:
            self.load_environment()
        return self.anthropic_api_key, self.perplexity_api_key