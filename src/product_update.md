# 変更仕様書

## 現状の実装

~/src/run.pyは二つのファイルを作成します
一つは~/doc/yyyy-mm-dd-topic.mdを作成します
これはMarpでスライドショーを作成するためのmarkdownです
もう一つはpodcast投稿用で~/_posts/yyyy-dd-mm-index.mdです
これは、podcastに投稿するfeedを作るベースのページになり、github pagesで投稿されます

run.pyは~/src/topic.yamlにある内容をもとに二つのファイルを作りますがほぼほぼ静的に作ります

## 変更仕様

現状のtopic.yamlの仕様に基づいて~/doc/yyyy-mm-dd-topic.mdの出力仕様を変更します
また、新規に~/youtube/というフォルダにyoutube概要欄に貼るべきものを自動生成するよう新規追加します
これらは~/_posts/yyyy-dd-mm-index.mdを作成するときと同じ生成結果をもとに作成するようにしてください

### ~/doc/yyyy-mm-dd-topic.md

これまでのスライドは以下のような内容でした
一部の抜粋であることに注意してください

```md
---
marp: true
theme: myformat
paginate: true
---

<!--
_class: normal
-->

![bg](./stringarea.png)
# 準天頂衛星みちびき6号機を打ち上げ成功

## 01. DeepSeekが低コストで高性能な推論モデルを公開
### 02. 準天頂衛星みちびき6号機を打ち上げ成功
### 03. 小惑星と誤認されたテスラ車、宇宙で再発見
---
<!--
_class: normal
-->

![bg](./stringarea.png)
# 準天頂衛星みちびき6号機を打ち上げ成功

### 01. DeepSeekが低コストで高性能な推論モデルを公開
## 02. 準天頂衛星みちびき6号機を打ち上げ成功
### 03. 小惑星と誤認されたテスラ車、宇宙で再発見
---
```

これを以下のように修正します
内容は箇条書きにしてください

```md
---
marp: true
theme: myformat
paginate: true
---

<!--
_class: normal
-->

![bg](./stringarea.png)
# 目次

1. 見出し1
2. 見出し2
3. 見出し3
4. 見出し4
5. 見出し5
6. 見出し6

---
<!--
_class: normal
-->

![bg](./stringarea.png)
# 見出し1

内容1の箇条書き
---
<!--
_class: normal
-->

![bg](./stringarea.png)
# 見出し2

内容2の箇条書き
---
以下略
```

### ~/youtube/yyyy-mm-dd-topic.md

以下の仕様で作成します
各見出しと内容を工夫してyoutube概要欄を作成してください

### YouTubeの概要欄の記載フォーマットと仕様

YouTubeの概要欄（説明文）は、動画の内容を視聴者やアルゴリズムに伝える重要な要素です。以下に、効果的な概要欄を作成するためのフォーマットや仕様、注意点をまとめます。

#### **概要欄の基本仕様**
- **文字数制限**: 最大5,000文字（半角）、または全角2,500文字まで入力可能[1][5][7]。
- **表示範囲**: 初めの約3行（150文字程度）が検索結果や動画ページで表示され、それ以降は「もっと見る」をクリックすることで表示されます[5][7]。
- **フォーマット**: テキストのみ入力可能ですが、以下の書式設定が可能です[1][7]。
  - 太字: `*テキスト*`
  - 斜体: `_テキスト_`
  - 取り消し線: `-テキスト-`
  - 箇条書き: `*`、`+`、`-` の後にスペースを入れる


#### **効果的な概要欄の構成**
1. **冒頭にキャッチコピーを記載**
   - 最初の2～3行に動画の内容を簡潔に説明し、視聴者の興味を引く文章を記載します。
   - 例: 「この動画では、初心者でも簡単にできるPythonプログラミングの基本を解説します！」[5][6][7]。

2. **キーワードを適切に配置**
   - 動画のテーマに関連する主要キーワードを3～4個含め、特に冒頭部分に配置します[5][6][7]。
   - キーワードは自然な文脈で使用し、過剰な「キーワード詰め込み」は避ける[6]。

3. **タイムスタンプを追加**
   - 長い動画の場合、視聴者が見たいセクションに直接アクセスできるようタイムスタンプを記載します。
   - 例: 
     ```
     00:00 - オープニング
     02:15 - 基本設定の説明
     05:30 - 実践例
     ```[5][6][7]。

4. **リンクやリソースを記載**
   - 動画内で紹介したウェブサイトや関連動画、SNSアカウントのリンクを記載します。
   - URLには簡単な説明文を添えることでクリック率を向上させます。
   - 例: 「詳細はこちら: [リンク]」[5][6][7]。

5. **行動を促すフレーズ（CTA）を含める**
   - 視聴者に次のアクションを促す文言を記載します。
   - 例: 「チャンネル登録はこちら: [リンク]」「コメントで感想を教えてください！」[6][7]。

6. **ハッシュタグを活用**
   - 動画に関連するハッシュタグを2～3個記載し、検索性を向上させます。
   - 注意: 15個以上のハッシュタグを記載すると無効化されるため、適切な数に留める[5][6]。


#### **注意点**
- **独自性を保つ**: 各動画にユニークな説明文を作成し、他の動画との差別化を図る[1][7]。
- **情報の更新**: 古いリンクや情報を放置せず、定期的に更新する[6]。
- **著作権の明記**: 使用した楽曲や素材のクレジットを記載する必要がある場合は忘れずに記載[5]。

#### **テンプレート例**
以下は、概要欄のテンプレート例です。

```
【動画内容】
この動画では、初心者向けにPythonプログラミングの基本を解説します。プログラミングを始めたい方に最適な内容です！

【タイムスタンプ】
00:00 - オープニング
02:15 - 基本設定の説明
05:30 - 実践例

【関連リンク】
- 詳細な解説記事: [リンク]
- チャンネル登録はこちら: [リンク]

【SNS】
- Instagram: [リンク]
- Twitter: [リンク]

#Python #プログラミング #初心者向け
```

#### **まとめ**
YouTubeの概要欄は、視聴者の興味を引き、動画の検索性を高める重要な要素です。キーワードの活用やタイムスタンプの追加、CTAの記載などを意識し、視聴者にとって分かりやすく魅力的な内容を心がけましょう。
[1] https://support.google.com/youtube/answer/12948449?hl=en
[2] https://clipchamp.com/ja/blog/youtube-video-descriptions/
[3] https://www.reddit.com/r/NewTubers/comments/17e18z3/what_should_we_actually_be_putting_in_the/
[4] https://www.reddit.com/r/NewTubers/comments/16a4c6t/youtube_description_template/
[5] https://service.aainc.co.jp/product/letrostudio/article/youtube-explanation
[6] https://www.infocubic.co.jp/blog/archives/15714/
[7] https://support.google.com/youtube/answer/12948449?hl=ja
[8] https://www.castmagic.io/post/youtube-description-template
[9] https://sproutsocial.com/insights/youtube-descriptions/
[10] https://taggbox.com/ja/blog/youtube-seo-best-practices/
[11] https://support.google.com/youtube/answer/2467968?hl=en
[12] https://www.clickminded.com/templates/seo/youtube-description-template/
[13] https://nox-web.com/column/youtube-consulting/youtube-summary-writing-method/
[14] https://shonan-web.jp/youtube-descriptions/
[15] https://support.google.com/youtube/answer/11895180?hl=ja
[16] https://youtubemasterd.com/2023/11/28/youtube-descriptionbox-how-to-write/
[17] https://blog.hootsuite.com/youtube-descriptions/
[18] https://coconala.com/blogs/664819/235044?srsltid=AfmBOopxYW2YnozqhFTTBNK1l_nW38DxdcSczc-1C6YMlvUXAnHJ2TkT
[19] https://coschedule.com/headlines/how-to-write-youtube-descriptions
[20] https://www.quora.com/How-do-I-write-a-description-for-my-YouTube-channel
[21] https://www.nogic.co.jp/column/youtube-summary-column
[22] https://www.linkedin.com/pulse/formatting-youtube-descriptions-best-practices-tips-leadsview-bkfqc
[23] https://media-hakase.com/column/article/page_2791.html
[24] https://textcortex.com/ja/post/youtube%E3%81%AE%E5%8B%95%E7%94%BB%E3%82%92seo%E3%81%AB%E6%9C%80%E9%81%A9%E5%8C%96%E3%81%99%E3%82%8B%E6%96%B9%E6%B3%95
[25] https://ucomm.stanford.edu/youtube-style-guide/
[26] https://communicationsguide.ucdavis.edu/departments/social-media/platform-best-practices/youtube-best-practices
[27] https://www.tubics.com/blog/youtube-description-text/
[28] https://www.tella.com/blog/youtube-description-examples-templates-copy
[29] https://artbrains.co.jp/article/document/817/
[30] https://moukegaku.com/youtube-seo-complete-guide/
[31] https://digital-hacks.jp/blog/archives/1385
[32] https://test0827.digital-hacks.jp/blog/archives/1385
[33] https://backlinko.com/hub/youtube/video-description
[34] https://www.quora.com/How-should-one-format-a-YouTube-videos-description
[35] https://pamxy.co.jp/marke-driven/sns-marketing/youtube/youtube-summary-column/
[36] https://www.agorapulse.com/blog/youtube/write-youtube-descriptions/
[37] https://unique1.co.jp/column/web_writing/15129/
[38] https://clipchamp.com/en/blog/youtube-video-descriptions/
[39] https://crobo.world/column/youtube-description/
[40] https://discovery.aoyako.com/youtube-description/
