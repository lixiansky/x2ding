/**
 * Cloudflare Worker - Twitter 图片代理
 * 
 * 部署说明:
 * 1. 登录 https://dash.cloudflare.com/
 * 2. 进入 Workers & Pages → Create Worker
 * 3. 粘贴此代码并部署
 * 4. 获得类似 https://img-proxy.your-name.workers.dev 的域名
 * 5. 将域名添加到 GitHub Secrets: CLOUDFLARE_PROXY
 * 
 * 使用方式:
 * https://your-worker.workers.dev?url=https://pbs.twimg.com/media/xxx.jpg
 */

export default {
    async fetch(request) {
        const url = new URL(request.url);

        // 获取图片 URL 参数
        const imageUrl = url.searchParams.get('url');

        if (!imageUrl) {
            return new Response('❌ 缺少 url 参数\n\n使用方式: ?url=https://pbs.twimg.com/media/xxx.jpg', {
                status: 400,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
        }

        // 验证 URL 格式
        let targetUrl;
        try {
            targetUrl = new URL(imageUrl);
        } catch (e) {
            return new Response('❌ 无效的 URL 格式', {
                status: 400,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
        }

        // 安全检查: 只允许 Twitter/X 相关域名
        const allowedDomains = [
            'pbs.twimg.com',
            'abs.twimg.com',
            'ton.twimg.com',
            'video.twimg.com'
        ];

        if (!allowedDomains.includes(targetUrl.hostname)) {
            return new Response(`❌ 不支持的域名: ${targetUrl.hostname}\n\n仅支持: ${allowedDomains.join(', ')}`, {
                status: 403,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
        }

        try {
            // 获取原始图片
            const response = await fetch(targetUrl.toString(), {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Referer': 'https://twitter.com/',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
                },
                cf: {
                    // Cloudflare 特定选项
                    cacheTtl: 86400,  // 缓存 24 小时
                    cacheEverything: true
                }
            });

            if (!response.ok) {
                return new Response(`❌ 获取图片失败: HTTP ${response.status}`, {
                    status: response.status,
                    headers: { 'Content-Type': 'text/plain; charset=utf-8' }
                });
            }

            // 返回图片,添加必要的响应头
            const headers = new Headers(response.headers);
            headers.set('Access-Control-Allow-Origin', '*');
            headers.set('Cache-Control', 'public, max-age=86400');
            headers.set('Content-Type', response.headers.get('Content-Type') || 'image/jpeg');

            // 删除可能导致问题的头
            headers.delete('Content-Security-Policy');
            headers.delete('X-Frame-Options');

            return new Response(response.body, {
                status: 200,
                headers: headers
            });

        } catch (error) {
            return new Response(`❌ 代理错误: ${error.message}`, {
                status: 500,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
        }
    }
};
