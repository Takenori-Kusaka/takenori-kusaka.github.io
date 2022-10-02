import logging
import yaml
import datetime
import glob

logger = logging.getLogger(__name__)



def generate_slide(now, topics: list):
    HEADER = "---\n\
marp: true\n\
theme: myformat\n\
paginate: true\n\
"

    TOPPAGE = "---\n\
\n\
<!--\n\
_class: top\n\
-->\n\
"

    PAGE_TEMPLATE = "---\n\
\n\
<!--\n\
_class: normal\n\
-->\n\
\n\
![bg](./stringarea.png)\n\
# Show Notes\n\
\n\
"

    TOPIC_HEADER = ['枕']
    for i in range(1, 7):
        TOPIC_HEADER.append('{0:02}'.format(i))

    logger.info(HEADER)
    logger.info(TOPPAGE)
    logger.info(PAGE_TEMPLATE)
    
    result = HEADER + TOPPAGE
    for t in topics:
        result = result + PAGE_TEMPLATE
        index = 0
        for tt in topics:
            if t == tt:
                result = result + '## '
            else:
                result = result + '### '
            result = result + TOPIC_HEADER[index] + '. '
            result = result + tt + '\n'
            index = index + 1
    
    logger.info(result)
    filename = now.strftime('%Y-%m-%d') + '-topic.md'
    filepath = './doc/' + filename
    logger.info(filepath)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(result)

def generate_post(now, topics: list):
    gl = glob.glob('./_posts/*.md')
    allposts = list(gl)
    allposts.sort()
    latest_post = allposts[-1].replace('.md', '').split('-')
    latest_num = int(latest_post[-1])
    latest_date = '{}-{}-{}'.format(latest_post[-4].split('\\')[-1], latest_post[-3], latest_post[-2])
    if latest_date == now.strftime('%Y-%m-%d'):
        pass
    else:
        latest_num = latest_num + 1
    filename = now.strftime('%Y-%m-%d') + '-{}.md'.format(latest_num)
    HEADER = "---\n\
actor_ids:\n\
- kokorokagami\n\
- touden\n\
audio_file_path: /audio/{0}\n\
audio_file_size: 0\n\
text_file_path: /text/{7}\n\
date: {1} 20:00:00 +0900\n\
description: kokorokagamiとtoudenの2人で、{2}{3} について話しました。\n\
duration: \"00:00\"\n\
layout: article\n\
title: {4}. {5} {6} ほか\n\
---\n\
".format(
        now.strftime('%Y%m%d') + 'm.m4a',
        now.strftime('%Y-%m-%d'),
        topics[1] if len(topics) > 1 else topics[0],
        "、{} など".format(topics[2]) if len(topics) > 2 else "",
        latest_num,
        now.strftime('%Y/%m/%d'),
        topics[0],
        now.strftime('%Y%m%d') + 'm.wav.vtt',
    )

    FOOTER = "\n\
___\n\
\n\
# こちらでも配信しています\n\
- [Youtube Live](https://www.youtube.com/channel/UCD1zo-WnyFdE5w0pqvKblkA)\n\
\n\
# ご意見、ご感想\n\
- [Twitter](https://twitter.com/recalog1)\n\
- [メールアドレス：rercalog@gmail.com](rercalog@gmail.com)\n\
\n\
# 編集\n\
\n\
@Touden氏  \n\
最大限の感謝を  \n\
\n\
# BGM\n\
\n\
[騒音のない世界](http://noiselessworld.net/) beco様より  \n\
OP:[オオカミ少年](https://soundcloud.com/baron1_3/wolfboy)  \n\
本編:[蜃気楼](https://soundcloud.com/baron1_3/shinkirou)  \n\
\n\
# 免責\n\
\n\
本ラジオはあくまで個人の見解であり現実のいかなる団体を代表するものではありません  \n\
ご理解頂ますようよろしくおねがいします  \n\
"

    TOPIC_HEADER = ['枕']
    for i in range(1, 7):
        TOPIC_HEADER.append('{}'.format(i))

    logger.info(HEADER)
    
    result = HEADER
    index = 0
    for t in topics:
        result = result + '\n'
        result = result + '# [{0}. {1}](TOPIC0_PAGELINK) (00:{2:02})\n\n'.format(TOPIC_HEADER[index], t, (index + 1) * 5)
        result = result + '[<img src="TOPIC0_IMGLINK" width="320dp">](TOPIC0_PAGELINK)\n'
        index = index + 1
    
    result = result + FOOTER
    logger.info(result)
    filepath = './_posts/' + filename
    logger.info(filepath)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(result)

def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')


    with open('./src/topic.yaml', encoding='utf-8') as f:
        topics = yaml.safe_load(f)
    generate_slide(topics['Date'], topics['Topic'])
    generate_post(topics['Date'], topics['Topic'])

if __name__ == "__main__":
    # execute only if run as a script
    main()
