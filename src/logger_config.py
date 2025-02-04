import logging
from logging.handlers import RotatingFileHandler

class LoggerConfig:
    @staticmethod
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