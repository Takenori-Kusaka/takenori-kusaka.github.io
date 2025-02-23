import glob
import logging
import re
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class ContentGenerator:
    def __init__(self):
        pass

    def extract_key_information(self, text, headline):
        """文から重要な情報を抽出"""
        # 主題を特定
        if '、' in headline:
            main_topic = headline.split('、')[0]
        else:
            main_topic = headline.split(' ')[0]

        # 不要な表現を削除
        remove_patterns = [
            'について', 'により', 'として', 'ところ', 'という', 'とされる',
            'と思われる', 'と考えられる', 'といった', 'などの', 'など',
            'とのこと', 'ようです', 'でした', 'である', 'あります',
            'のこと', 'という点', 'とされています'
        ]
        result = text
        for pattern in remove_patterns:
            result = result.replace(pattern, '')

        # 括弧と内容を一時的に保存
        brackets = {}
        def save_brackets(match):
            key = f"__BRACKET_{len(brackets)}__"
            brackets[key] = match.group(1)
            return key
        result = re.sub(r'（(.*?)）', save_brackets, result)
        result = re.sub(r'\((.*?)\)', save_brackets, result)

        # 主要な情報を含む部分を抽出
        parts = result.split('、')
        
        # 主題に関連する重要な情報を抽出
        keyword_parts = []
        info_parts = []
        
        for part in parts:
            # 数値を含む部分は優先的に保持
            if re.search(r'\d+(?:[,.]\d+)*(?:[万億兆]|%|倍)?', part):
                info_parts.append(part)
            # 主題に関連する部分を保持
            elif main_topic in part or any(kw in part for kw in main_topic.split()):
                keyword_parts.append(part)
            # 重要な動詞を含む部分を保持
            elif any(verb in part for verb in ['開発', '発表', '実現', '成功', '導入', '開始']):
                info_parts.append(part)

        # 結果を組み立て
        if keyword_parts:
            result = keyword_parts[0]  # 主題に最も関連する部分
            if info_parts:
                result += '、' + info_parts[0]  # 追加情報
        elif info_parts:
            result = info_parts[0]  # 重要な情報のみ
        else:
            result = parts[0]  # それ以外の場合は最初の部分

        # 文末表現を調整
        result = re.sub(r'(します|しました|された|されます|です|ます|でした|である|あります|なります|となります)$', '', result)

        # 重要な括弧内の情報を復元
        for key, value in brackets.items():
            if any(kw in value for kw in ['件', '円', '倍', '%', '万', '億']):
                result = result.replace(key, f"（{value}）")

        return result.strip()

    def format_bullet_point(self, text, max_length=35):
        """箇条書きを整形"""
        # テキストが空の場合はNoneを返す
        if not text or len(text.strip()) < 5:
            return None

        # 引用符を処理
        text = re.sub(r'「(.+?)」', r'\1', text)

        # 不要な記号を除去しつつ重要な情報を保持
        text = re.sub(r'(?<=[^0-9])。', '', text)  # 数字の後のピリオドは保持
        text = text.replace('、', ' ')

        # 数値と単位を一時的に保存
        number_map = {}
        def save_number(match):
            num = match.group(0)
            key = f"__NUM_{len(number_map)}__"
            number_map[key] = num
            return key

        # 数値を一時的に置換
        temp_text = re.sub(r'\d+(?:[,.]\d+)*(?:[万億兆]|%|倍)?', save_number, text)

        # 文を短くする
        words = temp_text.split()
        result = []
        length = 0
        for word in words:
            # 数値プレースホルダーの場合は元の数値の長さを使用
            if word.startswith('__NUM_'):
                orig_num = number_map.get(word, '')
                word_len = len(orig_num)
            else:
                word_len = len(word)
            
            if length + word_len > max_length - 3:
                break
            result.append(word)
            length += word_len

        # 数値を元に戻す
        core_text = ' '.join(result)
        for key, num in number_map.items():
            core_text = core_text.replace(key, num)

        # 末尾のスペースと記号を削除
        core_text = core_text.strip().rstrip('、。 ')

        # 長すぎる場合は省略
        if len(core_text) > max_length:
            core_text = core_text[:max_length-3] + '...'

        # 極端に短い場合はNoneを返す
        if len(core_text) < 5:
            return None

        return f"- {core_text}"

    def generate_bullet_points(self, summary, headline):
        """要約から箇条書きを生成"""
        # トピックに対応する重要なキーワードを定義
        topic_keywords = {
            'AI': ['性能', 'モデル', '開発', 'コスト', '学習'],
            '衛星': ['打ち上げ', '軌道', '運用', '技術', 'システム'],
            'テスラ': ['発見', '軌道', '観測', '天体', '宇宙']
        }

        # 文を意味のある単位で分割
        sections = []
        current = ""
        brackets_count = 0
        for char in summary:
            current += char
            if char == '（':
                brackets_count += 1
            elif char == '）':
                brackets_count -= 1
            elif char == '。' and brackets_count == 0 and not current.endswith(('氏。', '円。', '個。')):
                sections.append(current.strip())
                current = ""
        if current:
            sections.append(current.strip())

        # トピックに関連するキーワードを特定
        keywords = []
        for topic, topic_words in topic_keywords.items():
            if topic in headline:
                keywords.extend(topic_words)

        # セクションを重要度でソート
        scored_sections = []
        for section in sections:
            score = sum(2 if keyword in section else 0 for keyword in keywords)
            # 数値を含む場合はスコアを加算
            if re.search(r'\d+(?:[,.]\d+)*(?:[万億兆]|%|倍)?', section):
                score += 1
            scored_sections.append((score, section))
        
        # スコアの高い順にソート
        scored_sections.sort(reverse=True)

        # 箇条書きを生成
        bullet_points = []
        processed_sections = [section for _, section in scored_sections]
        
        for section in processed_sections[:4]:  # 最大4項目
            key_info = self.extract_key_information(section, headline)
            if key_info:
                point = self.format_bullet_point(key_info)
                if point and len(point) > 7:  # 極端に短い項目を除外
                    bullet_points.append(point)

        # 箇条書きが不足している場合は補完
        if len(bullet_points) < 2:
            context_points = {
                'AI': [
                    '- AIモデルの性能が大幅に向上',
                    '- 新技術により開発コストを削減'
                ],
                '衛星': [
                    '- 衛星システムの機能を拡充',
                    '- 最新技術による性能向上を実現'
                ],
                'テスラ': [
                    '- 宇宙空間での新たな発見',
                    '- 観測データの詳細を分析中'
                ]
            }
            for key, points in context_points.items():
                if key in headline and len(bullet_points) < 3:
                    for point in points:
                        if point not in bullet_points:
                            bullet_points.append(point)
                            if len(bullet_points) >= 3:
                                break

        return bullet_points

    def refine_slide_text(self, text, max_length=200):
        # スライド用にテキストを整形する
        refined = ' '.join(text.split())
        if len(refined) > max_length:
            refined = refined[:max_length-3] + "..."
        return refined

    def generate_slide_bullets(self, summary):
        """
        与えられたsummaryから最大3点の箇条書きを生成
        ※体言止め処理を削除し、原文をそのまま使用する
        """
        sentences = re.split(r'(?<=[。．?!])\s*', summary)
        bullets = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            # 末尾の句読点を除去
            s = re.sub(r'[。．？！]+$', '', s)
            # 体言止め変換の削除（該当行を削除）
            # 以前: s = re.sub(r'(する|です|ます|だった)$', '', s)
            # ※分割処理は削除しない
            if len(s) <= 3:
                continue
            bullets.append(f"- {s}")
            if len(bullets) >= 3:
                break
        # フォールバック（箇条書きが生成されなかった場合）
        if not bullets and summary.strip():
            fallback = re.sub(r'[。．?!]+$', '', summary.strip())
            # ※体言止め変換の削除（該当行を削除）
            if len(fallback) > 3:
                bullets.append(f"- {fallback}")
        return "\n".join(bullets)

    def generate_youtube_summary(self, summary):
        """YouTubeの説明用に140文字以内のサマリーを生成"""
        if len(summary) <= 140:
            return summary
        return summary[:137] + "..."

    def generate_youtube_description(self, date, headlines, youtube_summaries, main_title, latest_num):
        # Markdown形式のYouTube用説明文を作成する
        description = ""
        description += "---\n"
        description += f"第{latest_num}回 {main_title}\n"
        description += "---\n\n"
        description += "今回は以下のトピックについて話しました：\n\n"
        for idx, hl in enumerate(headlines, start=1):
            description += f"{idx}. {hl}\n"
        description += "\n【各トピックの詳細】\n"
        for idx, (hl, summary) in enumerate(zip(headlines, youtube_summaries), start=1):
            description += f"{idx}. {hl}\n{summary}\n\n"
        description += "【出演】\n"
        description += "kokorokagamiとtouden\n\n"
        description += "【免責】\n"
        description += "本ラジオはあくまで個人の見解であり現実のいかなる団体を代表するものではありません\n"
        description += "#テクノロジー #ニュース #エンジニアリング\n"
        return description

    def save_youtube_description(self, date, description):
        # 出力先のファイルパスを生成 (/youtube/フォルダ内)
        filename = date.strftime('%Y-%m-%d') + '-topic.md'
        output_path = os.path.join('./youtube', filename)
        print(output_path)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(description)
        except IOError as e:
            # ログ出力や例外処理
            print(f"ファイル書き込みエラー: {str(e)}")
            raise

    def generate_slide(self, date, headlines, summaries):
        logger.info("スライド生成開始")
        
        HEADER = """---
marp: true
theme: myformat
paginate: true
---

"""
        TABLE_OF_CONTENTS = """<!--
_class: normal
-->

![bg](./stringarea.png)
# 目次

{}
"""
        # 改行を明示している（区切り文字の前後に空行）
        CONTENT_PAGE = """<!--
_class: normal
-->

![bg](./stringarea.png)
# {}

{}

"""
        toc_items = []
        for i, headline in enumerate(headlines, 1):
            toc_items.append(f"{i}. {headline}")
        toc_content = TABLE_OF_CONTENTS.format('\n'.join(toc_items))
        
        content_pages = []
        for headline, summary in zip(headlines, summaries):
            # summaryから箇条書きを生成
            bullets = self.generate_slide_bullets(summary)
            page = CONTENT_PAGE.format(headline, bullets)
            # 複数スライドの間は前後に改行と区切りを入れる
            if content_pages:
                content_pages.append("\n---\n")
            content_pages.append(page)
        
        result = HEADER + toc_content + "\n---\n" + ''.join(content_pages)
        
        filename = date.strftime('%Y-%m-%d') + '-topic.md'
        filepath = './doc/' + filename
        logger.info(f"スライドファイル生成: {filepath}")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(result)
            logger.info("スライド生成完了")
            return True
        except IOError as e:
            logger.error(f"ファイル書き込みエラー: {str(e)}")
            raise

    def get_latest_post_number(self, date):
        """最新の投稿番号を取得"""
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
            return latest_num
        except Exception as e:
            logger.error(f"投稿番号取得エラー: {str(e)}")
            raise

    def generate_post(self, date, headlines, summaries, main_title, latest_num):
        """ブログ投稿用のMarkdownを生成"""
        logger.info("ブログ投稿生成開始")
        
        try:
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
            return True
        except Exception as e:
            logger.error(f"ブログ投稿生成エラー: {str(e)}")
            raise
