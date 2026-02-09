import os
import time
import random
import json
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup
import tempfile
import base64

# 配置
USERS_STR = os.environ.get('TWITTER_USER', 'elonmusk')
USERS = [u.strip() for u in USERS_STR.split(',') if u.strip()]
WEBHOOK_URL = os.environ.get('DINGTALK_WEBHOOK')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_ID_FILE = os.path.join(BASE_DIR, 'last_id.json')

# 运行模式配置
LOOP_MODE = os.environ.get('LOOP_MODE', 'false').lower() == 'true'
INTERVAL = int(os.environ.get('LOOP_INTERVAL', '600')) # 默认 10 分钟 (600秒)

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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
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
                try:
                    response = page.goto(url, wait_until="networkidle", timeout=45000)
                    if response and response.status == 403:
                        print(f"[{target}] 访问 {instance} 被拒 (403 Forbidden)")
                        context.close()
                        continue
                except Exception as e:
                    print(f"[{target}] 加载 {instance} 超时或失败: {e}")
                    context.close()
                    continue
                
                # 智能等待浏览器验证或"稍等片刻"挑战
                challenge_keywords = ["Verifying your browser", "Just a moment", "Checking your browser"]
                for i in range(5): # 最多等待 25 秒
                    content = page.content()
                    if any(kw in content for kw in challenge_keywords):
                        print(f"[{target}] 检测到浏览器验证 ({i+1}/5)，尝试等待...")
                        page.wait_for_timeout(5000)
                    else:
                        break
                
                # 获取最终渲染后的 HTML
                soup = BeautifulSoup(page.content(), 'html.parser')
                
                # Nitter 页面推文解析逻辑
                items = soup.select('.timeline-item')
                if not items:
                    print(f"[{target}] 在实例 {instance} 上未发现推文内容")
                    context.close()
                    continue
                
                # 扫描策略：扫描前 8 条推文，找到第一条非置顶的、有效的内容
                valid_tweets = []
                for item in items[:8]:
                    # 1. 检查是否是置顶推文 (移除 "Pinned" text 匹配以防止误伤推文内容)
                    is_pinned = item.select_one('.pinned') is not None
                    if is_pinned:
                        print(f"[{target}] 发现置顶推文，跳过")
                        continue
                    
                    # 2. 检查是否是转发
                    is_retweet = item.select_one('.retweet-header') is not None

                    # 3. 提取图片 (增加更多可能的 Nitter 图片选择器)
                    images = []
                    img_els = item.select('.attachment.image img, .tweet-image img, .still-image img, .attachments img')
                    for img in img_els:
                        # 排除头像 (通常在 .tweet-avatar 或 .profile-card-avatar 中)
                        if any(c in str(img.parent.get('class', [])) for c in ['avatar', 'profile']):
                            continue
                            
                        src = img.get('src', '')
                        if src:
                            # 转换相对路径
                            if src.startswith('//'):
                                full_src = 'https:' + src
                            elif src.startswith('/'):
                                full_src = instance.rstrip('/') + src
                            else:
                                full_src = src
                            
                            # 还原原始 Twitter 图片链接以提高代理稳定性
                            full_src = get_original_image_url(full_src)
                            
                            # 过滤掉一些明显的表情包或小图标 (可选)
                            if 'emoji' in src.lower() or 'hashtag_click' in src:
                                continue
                                
                            images.append(full_src)

                    # 4. 提取视频 (新增)
                    video_url = None
                    try:
                        video_el = item.select_one('video source')
                        if not video_el:
                            video_el = item.select_one('video')
                        
                        if video_el:
                            # 尝试获取封面图作为额外图片
                            poster_el = item.select_one('video')
                            if poster_el:
                                poster = poster_el.get('poster', '')
                                if poster:
                                    if poster.startswith('//'):
                                        full_poster = 'https:' + poster
                                    elif poster.startswith('/'):
                                        full_poster = instance.rstrip('/') + poster
                                    else:
                                        full_poster = poster
                                    # 尝试还原原始封面图地址并加入图片列表
                                    full_poster = get_original_image_url(full_poster)
                                    if full_poster not in images:
                                        images.append(full_poster)

                            # 提取视频流地址
                            v_src = video_el.get('src', '')
                            if v_src:
                                if v_src.startswith('//'):
                                    video_url = 'https:' + v_src
                                elif v_src.startswith('/'):
                                    video_url = instance.rstrip('/') + v_src
                                else:
                                    video_url = v_src
                    except Exception as e:
                        print(f"[{target}] 视频提取异常: {e}")

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
                        'images': images,
                        'video_url': video_url
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

def upload_to_imgbb(image_url):
    """
    上传图片到 ImgBB 图床
    需要配置环境变量: IMGBB_API_KEY
    """
    api_key = os.environ.get('IMGBB_API_KEY', '').strip()
    if not api_key:
        print("[图床] ImgBB 未配置 API Key, 无法上传")
        return None
    
    try:
        # 下载图片
        print(f"[图床] 正在从 {image_url} 下载图片...")
        img_response = requests.get(image_url, timeout=30, headers={
            'User-Agent': get_random_user_agent(),
            'Referer': 'https://twitter.com/'
        })
        img_response.raise_for_status()
        
        # 转换为 base64
        img_base64 = base64.b64encode(img_response.content).decode('utf-8')
        
        # 上传到 ImgBB
        print("[图床] 正在上传到 ImgBB...")
        upload_response = requests.post(
            'https://api.imgbb.com/1/upload',
            data={
                'key': api_key,
                'image': img_base64
            },
            timeout=30
        )
        result = upload_response.json()
        
        if result.get('success'):
            url = result['data']['url']
            print(f"[图床] ImgBB 上传成功: {url}")
            return url
        else:
            print(f"[图床] ImgBB 上传失败: {result}")
            return None
    except Exception as e:
        print(f"[图床] ImgBB 上传异常: {e}")
        return None

def upload_image_to_bed(image_url):
    """
    上传图片到 ImgBB 图床
    """
    return upload_to_imgbb(image_url)



def send_dingtalk(webhook_url, tweet, target):
    """
    发送钉钉消息
    """
    if not webhook_url:
        print("未配置 DINGTALK_WEBHOOK，跳过发送")
        return False

    retweet_flag = " 🔃 转发了" if tweet.get('is_retweet') else " 📝 发布了"
    
    # 尝试翻译内容
    print(f"[{target}] 正在翻译推文内容...")
    
    # 清理原文中的乱码或装饰性字符
    raw_content = tweet['content']
    # 移除特定乱码序列 €∋
    clean_content = raw_content.replace('€∋', '').strip()
    
    translated_content = translate_text(clean_content)
    
    # 构造内容展示 (如果有翻译则显示翻译+原文)
    if translated_content:
        display_content = f"""**翻译**: {translated_content}\n\n**原文**: {raw_content}"""
    else:
        display_content = f"""{raw_content}"""

    # 构造图片 Markdown (优先使用图床,回退到代理)
    images_md = ""
    if tweet.get('images'):
        # 检查是否启用图床上传
        use_image_bed = os.environ.get('USE_IMAGE_BED', 'true').lower() == 'true'
        
        for img_url in tweet['images']:
            import urllib.parse
            
            final_url = None
            
            # 方案1: 尝试上传到图床 (推荐)
            if use_image_bed:
                print(f"[{target}] 正在上传图片到图床...")
                final_url = upload_image_to_bed(img_url)
            
            # 方案2: 如果图床失败,使用代理服务
            if not final_url:
                cloudflare_proxy = os.environ.get('CLOUDFLARE_PROXY', '').strip()
                if cloudflare_proxy:
                    encoded_url = urllib.parse.quote(img_url)
                    final_url = f"{cloudflare_proxy.rstrip('/')}?url={encoded_url}"
                else:
                    # 回退到 wsrv.nl 代理
                    clean_url = img_url.replace('https://', '').replace('http://', '')
                    encoded_url = urllib.parse.quote(clean_url)
                    final_url = f"https://wsrv.nl/?url={encoded_url}"
            
            if final_url:
                images_md += f"\n\n![image]({final_url})"

    # 如果有视频链接，添加观看链接
    if tweet.get('video_url'):
        images_md += f"\n\n[🎬 点击观看视频]({tweet['video_url']})"

    title = f"Twitter 监控: {target}"
    text = f"""## {target}{retweet_flag} 推文
---
**作者**: {tweet['author']}
**时间**: {tweet['published']}

> {display_content}
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

def get_original_image_url(nitter_url):
    """
    尝试从 Nitter 的代理 URL 中还原出 Twitter/X 的原始图片地址
    例如: /pic/media%2FGDR-yXfbsAA_JmS.jpg -> pbs.twimg.com
    """
    import urllib.parse
    import re
    try:
        if 'pbs.twimg.com' in nitter_url:
            return nitter_url
            
        # 1. 处理 hex 编码的对象 (常见于 xcancel 等实例)
        if '/pic/enc/' in nitter_url:
            enc_part = nitter_url.split('/pic/enc/')[-1].split('?')[0]
            try:
                decoded = bytes.fromhex(enc_part).decode('utf-8')
                if 'pbs.twimg.com' in decoded:
                    return decoded
            except:
                pass

        # 2. 处理标准 Nitter 路径
        path = urllib.parse.unquote(nitter_url)
        
        # 匹配 /pic/media/ID.ext 或 /pic/orig/media/ID.ext
        if '/media/' in path:
            media_part = path.split('/media/')[-1].split('?')[0]
            if '.' in media_part:
                media_id, ext = media_part.rsplit('.', 1)
                # 某些时候 ext 后面可能还跟着 &name=...
                ext = ext.split('&')[0].split('?')[0]
                return f"https://pbs.twimg.com/media/{media_id}?format={ext}&name=large"

        # 3. 处理直接包含 pbs.twimg.com 的路径 (如 /pic/pbs.twimg.com/media/...)
        if 'pbs.twimg.com' in path:
            # 提取从 pbs.twimg.com 开始的部分
            match = re.search(r'(pbs\.twimg\.com/media/[^?&]+)', path)
            if match:
                return "https://" + match.group(1)

    except Exception as e:
        print(f"[图片解析] 还原 URL 失败 {nitter_url}: {e}")
        
    return nitter_url

def translate_text(text, target_lang='zh-CN'):
    """
    使用 Google Translate (GTX) 接口进行免费翻译
    """
    if not text or not text.strip():
        return ""
    
    # 简单的翻译逻辑
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        
        # 解析返回的 JSON
        data = resp.json()
        if data and data[0]:
            translated_parts = [part[0] for part in data[0] if part[0]]
            return "".join(translated_parts)
    except Exception as e:
        print(f"[翻译] 失败: {e}")
    
    return None

def main():
    if not USERS:
        print("没有配置监控目标")
        return

    print(f"[{datetime.now()}] 启动监控模式 (LOOP_MODE={LOOP_MODE}, INTERVAL={INTERVAL}s)...")
    
    # 从本地缓存加载可用实例
    instances = load_instances()

    while True:
        cycle_start = time.time()
        print(f"\n--- 启动新一轮监控轮询 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
        
        # 加载状态 (每轮都重新加载，防止外部手动修改或异常)
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
                    print(f"[{target}] 无视更新 (ID 未变)")
            except Exception as e:
                print(f"[{target}] 处理异常: {e}")

        if updated:
            with open(LAST_ID_FILE, 'w', encoding='utf-8') as f:
                json.dump(last_ids, f, indent=2, ensure_ascii=False)
            print("[系统] 状态文件已更新")

        if not LOOP_MODE:
            print("[系统] 非循环模式，任务结束。")
            break
        
        # 计算需要 sleep 的时间，减去已经消耗的时间
        elapsed = time.time() - cycle_start
        sleep_time = max(10, INTERVAL - elapsed)
        print(f"--- 轮询结束。耗时 {elapsed:.1f}s，准备休眠 {sleep_time:.1f}s ---\n")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
