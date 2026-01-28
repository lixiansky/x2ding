import os
import time
import random
import json
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup

# 配置
USERS_STR = os.environ.get('TWITTER_USER', 'elonmusk')
USERS = [u.strip() for u in USERS_STR.split(',') if u.strip()]
WEBHOOK_URL = os.environ.get('DINGTALK_WEBHOOK')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_ID_FILE = os.path.join(BASE_DIR, 'last_id.json')

# 备选 Nitter 实例 (仅作为域名参考)
NITTER_INSTANCES = [
    'https://xcancel.com',
    'https://nitter.privacyredirect.com',
    'https://nitter.poast.org',
    'https://nitter.hu',
    'https://nitter.moomoo.me',
    'https://nitter.net',
]

INSTANCES_FILE = os.path.join(BASE_DIR, 'instances.json')

def get_random_user_agent():
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0"
    ]
    return random.choice(ua_list)

def load_instances():
    """
    从本地缓存加载健康的 Nitter 实例
    """
    if os.path.exists(INSTANCES_FILE):
        try:
            with open(INSTANCES_FILE, 'r', encoding='utf-8') as f:
                instances = json.load(f)
                if instances and isinstance(instances, list):
                    print(f"[系统] 成功从本地缓存加载 {len(instances)} 个实例")
                    return instances
        except Exception as e:
            print(f"[系统] 加载实例缓存失败: {e}")
    
    print("[系统] 缓存不存在或损坏，采用内置兜底实例列表")
    return NITTER_INSTANCES

def scrape_nitter_with_playwright(target, dynamic_instances=None):
    """
    使用 Playwright 模拟浏览器访问 Nitter 并抓取最新推文
    """
    is_search = target.startswith('search:')
    keyword = target[7:] if is_search else target
    
    # 优先使用动态获取的实例，如果没有则用内置的
    instances = dynamic_instances if dynamic_instances else NITTER_INSTANCES.copy()
    # 为了分布压力，我们在保持高分实例在前的前提下，对前 5 名进行小范围随机
    if len(instances) > 5:
        top_5 = instances[:5]
        random.shuffle(top_5)
        others = instances[5:]
        random.shuffle(others)
        instances = top_5 + others
    else:
        random.shuffle(instances)
    
    with sync_playwright() as p:
        # 启动浏览器 (头模式/无头模式取决于环境，GitHub Actions 建议 headless=True)
        browser = p.chromium.launch(headless=True)
        
        for instance in instances:
            try:
                # 每个实例创建一个新上下文，模拟干净的访问
                context = browser.new_context(
                    user_agent=get_random_user_agent(),
                    viewport={'width': 1280, 'height': 720}
                )
                page = context.new_page()
                
                # 应用 Stealth 插件绕过检测
                stealth_sync(page)
                
                if is_search:
                    url = f"{instance.rstrip('/')}/search?f=tweets&q={requests.utils.quote(keyword)}"
                else:
                    url = f"{instance.rstrip('/')}/{keyword}"
                
                print(f"[{target}] 正在加载: {url}")
                
                # 开始加载并处理可能的挑战
                response = page.goto(url, wait_until="networkidle", timeout=45000)
                
                # 如果看到 "Verifying your browser"，等待其消失
                if "Verifying your browser" in page.content():
                    print(f"[{target}] 检测到浏览器验证，尝试等待...")
                    # 某些验证需要一点时间自动跳转
                    page.wait_for_timeout(5000)
                
                # 获取最终渲染后的 HTML
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Nitter 页面推文解析逻辑
                items = soup.select('.timeline-item')
                if not items:
                    print(f"[{target}] 在实例 {instance} 上未发现推文内容")
                    context.close()
                    continue
                
                # 扫描策略：扫描前 5 条推文，找到第一条非置顶的、有效的内容
                valid_tweets = []
                for item in items[:8]: # 扩大扫描范围到前 8 条
                    # 1. 检查是否是置顶推文
                    is_pinned = item.select_one('.pinned') or "Pinned" in item.get_text()
                    if is_pinned:
                        print(f"[{target}] 发现置顶推文，跳过扫描")
                        continue
                    
                    # 2. 检查是否是转发
                    is_retweet = item.select_one('.retweet-header') is not None

                    # 3. 提取图片
                    images = []
                    # Nitter 的图片通常在 .attachment.image 或 .tweet-image 中
                    img_els = item.select('.attachment.image img, .tweet-image img')
                    for img in img_els:
                        src = img.get('src', '')
                        if src:
                            # 转换相对路径
                            full_src = instance.rstrip('/') + src if src.startswith('/') else src
                            images.append(full_src)

                    # 提取关键信息
                    content_el = item.select_one('.tweet-content')
                    link_el = item.select_one('.tweet-link')
                    date_el = item.select_one('.tweet-date a')
                    author_el = item.select_one('.username')

                    if not content_el or not link_el:
                        continue

                    # 提取推文 ID (从 /user/status/123...#m 中提取数字)
                    link_href = link_el.get('href', '')
                    tweet_id = link_href.split('/status/')[-1].split('#')[0] if '/status/' in link_href else link_href

                    tweet_data = {
                        'content': content_el.get_text(strip=True),
                        'link': instance.rstrip('/') + link_href,
                        'published': date_el.get('title', '') if date_el else 'Unknown Time',
                        'author': author_el.get_text(strip=True) if author_el else keyword,
                        'guid': tweet_id,
                        'is_retweet': is_retweet,
                        'images': images
                    }
                    valid_tweets.append(tweet_data)
                    
                    # 只要找到了第一个非置顶的有效推文，我们就认为它是当前“最新的”
                    if len(valid_tweets) >= 1:
                        break

                if valid_tweets:
                    tweet = valid_tweets[0]
                    retweet_tag = " [转发]" if tweet['is_retweet'] else ""
                    print(f"[{target}] 成功从 {instance} 抓取{retweet_tag}推文: {tweet['guid']}")
                    context.close()
                    browser.close()
                    return tweet

                print(f"[{target}] {instance} 页面上未找到符合条件的非置顶推文")
                context.close()

            except Exception as e:
                print(f"[{target}] 访问 {instance} 出错: {e}")
                continue
        
        browser.close()
    return None

def send_dingtalk(webhook_url, tweet, target):
    """
    发送钉钉消息
    """
    if not webhook_url:
        print("未配置 DINGTALK_WEBHOOK，跳过发送")
        return False

    retweet_flag = " 🔃 转发了" if tweet.get('is_retweet') else " 📝 发布了"
    
    # 构造图片 Markdown (使用 weserv.nl 代理解决国内钉钉加载不出的问题)
    images_md = ""
    if tweet.get('images'):
        for img_url in tweet['images']:
            # 编码 URL 并包装代理
            proxied_url = f"https://images.weserv.nl/?url={requests.utils.quote(img_url.replace('https://', '').replace('http://', ''))}"
            images_md += f"\n\n![image]({proxied_url})"

    title = f"Twitter 监控: {target}"
    text = f"""## {target}{retweet_flag} 推文
---
**作者**: {tweet['author']}
**时间**: {tweet['published']}

> {tweet['content']}
{images_md}

---
[🔗 Nitter 原文]({tweet['link']}) | [🔗 Twitter(X) 原文]({tweet['link'].replace('xcancel.com', 'twitter.com').replace('nitter.net', 'twitter.com').replace('nitter.hu', 'twitter.com').replace('nitter.privacyredirect.com', 'twitter.com').replace('nitter.poast.org', 'twitter.com')})
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
        result = resp.json()
        if result.get('errcode') == 0:
            print(f"[{target}] 钉钉推送成功")
            return True
        else:
            print(f"[{target}] 钉钉推送失败: {result}")
            return False
    except Exception as e:
        print(f"[{target}] 钉钉请求异常: {e}")
        return False

def main():
    if not USERS:
        print("没有配置监控目标")
        return

    print(f"[{datetime.now()}] 启动 Playwright 反检测监控模式...")
    
    # 从本地缓存加载可用实例
    instances = load_instances()

    # 加载状态
    if os.path.exists(LAST_ID_FILE):
        try:
            with open(LAST_ID_FILE, 'r', encoding='utf-8') as f:
                last_ids = json.load(f)
        except: last_ids = {}
    else: last_ids = {}

    updated = False
    for target in USERS:
        try:
            tweet = scrape_nitter_with_playwright(target, instances)
            if not tweet:
                continue
            
            current_id = tweet['guid']
            if last_ids.get(target) != current_id:
                print(f"[{target}] 发现更新: {current_id}")
                if send_dingtalk(WEBHOOK_URL, tweet, target):
                    last_ids[target] = current_id
                    updated = True
            else:
                print(f"[{target}] 无视更新")
        except Exception as e:
            print(f"[{target}] 总体处理异常: {e}")

    if updated:
        with open(LAST_ID_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_ids, f, indent=2, ensure_ascii=False)
        print("状态文件已更新")

if __name__ == "__main__":
    main()
