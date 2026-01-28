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

def get_random_user_agent():
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0"
    ]
    return random.choice(ua_list)

def scrape_nitter_with_playwright(target):
    """
    使用 Playwright 模拟浏览器访问 Nitter 并抓取最新推文
    """
    is_search = target.startswith('search:')
    keyword = target[7:] if is_search else target
    
    instances = NITTER_INSTANCES.copy()
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
                # 推文容器通常是 timeline-item
                items = soup.select('.timeline-item')
                if not items:
                    print(f"[{target}] 在实例 {instance} 上未发现推文内容")
                    context.close()
                    continue
                
                # 获取第一条有效推文（排除置顶或无关项，通常第一条就是）
                first_item = items[0]
                
                # 提取关键信息
                content_el = first_item.select_one('.tweet-content')
                link_el = first_item.select_one('.tweet-link')
                date_el = first_item.select_one('.tweet-date a')
                author_el = first_item.select_one('.username')

                if not content_el or not link_el:
                    context.close()
                    continue

                tweet_data = {
                    'content': content_el.get_text(strip=True),
                    'link': instance.rstrip('/') + link_el.get('href', ''),
                    'published': date_el.get('title', '') if date_el else 'Unknown Time',
                    'author': author_el.get_text(strip=True) if author_el else keyword,
                    'guid': link_el.get('href', '') # 唯一标识
                }

                print(f"[{target}] 成功从 {instance} 抓取推文")
                context.close()
                browser.close()
                return tweet_data

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

    title = f"【Twitter】监控提醒: {target}"
    text = f"""### {title}
    
**作者**: {tweet['author']}
**时间**: {tweet['published']}
    
**内容**: 
{tweet['content']}
    
[查看详情 (Nitter)]({tweet['link']})
[查看详情 (Twitter)]({tweet['link'].replace('xcancel.com', 'twitter.com').replace('nitter.net', 'twitter.com').replace('nitter.hu', 'twitter.com')})
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
        return resp.json().get('errcode') == 0
    except Exception:
        return False

def main():
    if not USERS:
        print("没有配置监控目标")
        return

    print(f"[{datetime.now()}] 启动 Playwright 反检测监控模式...")
    
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
            tweet = scrape_nitter_with_playwright(target)
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
