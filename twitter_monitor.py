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

# Nitter 实例列表
NITTER_INSTANCES = [
    'https://nitter.net',
    'https://nitter.cz',
    'https://nitter.io',
    'https://nitter.privacydev.net',
    'https://nitter.projectsegfau.lt'
]

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

def get_latest_tweet(user):
    """
    尝试从 Nitter 实例获取最新推文 RSS
    """
    instances = NITTER_INSTANCES.copy()
    random.shuffle(instances)

    for instance in instances:
        rss_url = f"{instance}/{user}/rss"
        # print(f"正在尝试获取 {user}: {rss_url}")
        
        try:
            resp = requests.get(rss_url, headers=get_headers(), timeout=10)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    print(f"[{user}] 成功从 {instance} 获取数据")
                    return feed.entries[0]
                else:
                    print(f"[{user}] {instance} 返回空数据")
            else:
                pass
                # print(f"[{user}] {instance} 响应状态码: {resp.status_code}")
                
        except Exception as e:
            pass
            # print(f"[{user}] 访问 {instance} 失败: {e}")
            
    print(f"[{user}] 所有 Nitter 实例均尝试失败")
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
