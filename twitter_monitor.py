import os
import time
import requests
import feedparser
import random
import json
from datetime import datetime

# 配置
# 支持逗号分隔的多个用户，例如: "elonmusk,NASA,SpaceX"
USERS_STR = os.environ.get('TWITTER_USER', 'elonmusk')
USERS = [u.strip() for u in USERS_STR.split(',') if u.strip()]
WEBHOOK_URL = os.environ.get('DINGTALK_WEBHOOK')

# 脚本所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_ID_FILE = os.path.join(BASE_DIR, 'last_id.json')

# Nitter 实例列表 (综合 Wiki 及 status.d420.de 实时状态)
NITTER_INSTANCES = [
    'https://xcancel.com',
    'https://nitter.privacyredirect.com',
    'https://nitter.poast.org',
    'https://nitter.hu',
    'https://nitter.moomoo.me',
    'https://nitter.privacydev.net',
    'https://nitter.rawbit.ninja',
    'https://nitter.perennialte.ch',
    'https://nitter.projectsegfau.lt',
    'https://nitter.privacy.com.de',
    'https://nitter.no-logs.com',
    'https://nitter.net',  # 兜底
]

# RSSHub 实例列表 (更广泛的公共节点)
RSSHUB_INSTANCES = [
    'https://rsshub.app',
    'https://rsshub.rssbuddy.com',
    'https://rss.arturpaiva.top',
    'https://hub.076.ne.jp',
    'https://rsshub.anyant.com',
    'https://rsshub.icu'
]

def get_headers(instance_url=None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    }
    if instance_url:
        headers['Referer'] = instance_url
    return headers

def is_bot_challenge(content):
    """
    检查页面内容是否为机器人挑战或拦截页
    """
    if not content:
        return True
    indicators = [
        b'Verifying your browser',
        b'Checking your browser',
        b'Cloudflare',
        b'challenge-platform',
        b'RSS reader not yet whitelisted'
    ]
    return any(ind in content for ind in indicators)

def get_latest_tweet(target):
    """
    尝试从 Nitter 或 RSSHub 获取最新推文 RSS
    target 可以是用户名 (elonmusk) 或搜索词 (search:关键词)
    """
    is_search = target.startswith('search:')
    keyword = target[7:] if is_search else target
    
    # 获取混淆后的实例列表
    nitters = NITTER_INSTANCES.copy()
    random.shuffle(nitters)
    hubs = RSSHUB_INSTANCES.copy()
    random.shuffle(hubs)

    # 策略优先级：如果是搜索词监控，优先走 RSSHub，因为 Nitter 搜索限制极多
    strategies = []
    if is_search:
        strategies = [('RSSHub', hubs), ('Nitter', nitters)]
    else:
        strategies = [('Nitter', nitters), ('RSSHub', hubs)]

    for source_type, instances in strategies:
        for instance in instances:
            if source_type == 'Nitter':
                if is_search:
                    # Nitter 搜索 RSS 路由
                    rss_url = f"{instance.rstrip('/')}/search/rss?f=tweets&q={requests.utils.quote(keyword)}"
                else:
                    # Nitter 用户 RSS 路由
                    rss_url = f"{instance.rstrip('/')}/{keyword}/rss"
            else:
                if is_search:
                    # RSSHub 搜索路由
                    rss_url = f"{instance.rstrip('/')}/twitter/keyword/{requests.utils.quote(keyword)}"
                else:
                    # RSSHub 用户路由
                    rss_url = f"{instance.rstrip('/')}/twitter/user/{keyword}"

            try:
                resp = requests.get(rss_url, headers=get_headers(instance), timeout=25)
                
                # 机器人挑战检测
                if is_bot_challenge(resp.content):
                    print(f"[{target}] {source_type} ({instance}) 检测到机器人验证/白名单拦截，跳过")
                    continue

                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    if feed.entries:
                        print(f"[{target}] 成功通过 {source_type} ({instance}) 获取数据")
                        return feed.entries[0]
                    else:
                        print(f"[{target}] {source_type} ({instance}) 返回 200 但没有发现推文")
                else:
                    # print(f"[{target}] {source_type} ({instance}) 异常: {resp.status_code}")
                    pass
            except Exception:
                continue

    print(f"[{target}] 所有方法均未成功获取数据。")
    return None

def send_dingtalk(webhook_url, tweet, user):
    """
    发送钉钉消息
    """
    if not webhook_url:
        print("未配置 DINGTALK_WEBHOOK，跳过发送")
        return

    author = tweet.get('author', user)
    content = tweet.get('title', 'No Content')
    link = tweet.get('link', '')
    published = tweet.get('published', '')

    title = f"【Twitter】{author} 发布了新推文"
    text = f"""### {title}
    
**时间**: {published}
    
**内容**: 
{content}
    
[查看原文 (Nitter)]({link})
[查看原文 (Twitter)]({link.replace('nitter.net', 'twitter.com').replace('nitter.cz', 'twitter.com').replace('nitter.io', 'twitter.com')})
    """

    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        }
    }

    try:
        resp = requests.post(webhook_url, json=data, timeout=10)
        if resp.json().get('errcode') == 0:
            print(f"[{user}] 钉钉推送成功")
            return True
        else:
            print(f"[{user}] 钉钉推送失败: {resp.text}")
            return False
    except Exception as e:
        print(f"[{user}] 钉钉请求异常: {e}")
        return False

def load_last_ids():
    if os.path.exists(LAST_ID_FILE):
        try:
            with open(LAST_ID_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_ids(data):
    with open(LAST_ID_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("已更新状态文件")

def main():
    print(f"[{datetime.now()}] 开始检查 {len(USERS)} 个用户: {USERS}")
    
    last_ids = load_last_ids()
    updated = False

    for user in USERS:
        try:
            # 随机延迟，避免对实例造成过大压力
            time.sleep(random.uniform(1, 3))
            
            latest_entry = get_latest_tweet(user)
            if not latest_entry:
                continue

            current_id = latest_entry.get('guid') or latest_entry.get('link')
            if not current_id:
                continue

            last_id = last_ids.get(user)
            
            if current_id != last_id:
                print(f"[{user}] 发现新推文: {current_id}")
                success = send_dingtalk(WEBHOOK_URL, latest_entry, user)
                if success:
                    last_ids[user] = current_id
                    updated = True
            else:
                print(f"[{user}] 无新推文")
                
        except Exception as e:
            print(f"[{user}] 处理出错: {e}")

    if updated:
        save_last_ids(last_ids)

if __name__ == "__main__":
    main()
