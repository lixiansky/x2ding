# Twitter (X) 智能监控机器人 🤖

这是一个基于 **Playwright Stealth** 技术的工业级推文监控方案。它通过模拟真实浏览器行为，完美绕过屏蔽与机器人检测，将 Twitter 动态（含文字、图片、翻译、转发）实时推送到您的钉钉。

本项目专为 **GitHub Actions** 设计，全自动运行，无需自备服务器，同时也支持本地循环模式。

## ✨ 核心亮点

*   **🛡️ 强力反检测**: 放弃传统的 RSS 接口，采用 **Playwright 浏览器自动化** + Stealth 插件。自动模拟人类点击，轻松穿透 Nitter 验证码与访问限制。
*   **🌐 自动翻译与清理**: 
    *   **一键翻译**: 集成 Google Translate (GTX) 接口，自动将推文翻译为中文，方便快速阅读。
    *   **智能清洗**: 自动识别并移除推文中的装饰性乱码（如 `€∋` 等），提供纯净的阅读体验。
*   **🖼️ 完美图文展示**: 
    *   **高级图片解析**: 内置复杂的 URL 还原逻辑，能够识别并从 Nitter 的加密/代理路径（如 `xcancel` 的 hex 编码 URL）中还原出原始 `pbs.twimg.com` 地址。
    *   **稳定透明代理**: 使用 `wsrv.nl` (weserv.nl) 代理服务，确保国内钉钉客户端能够稳定加载推文配图。
*   **📡 自动发现可用节点**: 集成实例探测逻辑，定期自动扫描全球 Nitter 节点，动态优选最稳、最快的“健康实例”。
*   **🧠 智能过滤逻辑**: 自动识别并跳过博主的**置顶推文 (Pinned Tweets)**，确保只在发布真正的“新鲜项”时才报警。

## 🚀 部署指南

### 第一步：代码就绪
确保您的 GitHub 仓库根目录中包含以下核心文件：
```text
repo-root/
├── .github/workflows/
│   ├── main.yml             (主监控流水线)
│   └── update_instances.yml (实例同步流水线)
├── twitter_monitor.py       (核心抓取与推送程序)
├── update_instances.py      (实例自动化发现工具)
├── requirements.txt         (支持 Playwright & BeautifulSoup)
└── README.md
```

### 第二步：配置钉钉机器人
1. 钉钉群组 -> 设置 -> 智能群助手 -> 添加机器人 -> 自定义。
2. **安全设置**：选择“自定义关键词”，填入：`Twitter`。
3. 复制生成的 Webhook URL。

### 第三步：设置环境变量 (Secrets)
在 GitHub 仓库 **Settings -> Secrets and variables -> Actions** 中添加：

| Secret Name | 示例 Value | 说明 |
|-------------|------------|------|
| `TWITTER_USER` | `elonmusk` 或 `search:关键词` | 监控目标。**多个请用英文逗号分隔**。 |
| `DINGTALK_WEBHOOK` | `https://oapi.dingtalk.com/...` | 钉钉机器人 Webhook 地址 |
| `LOOP_MODE` | `true/false` | [可选] 是否开启循环模式 (GitHub Actions 建议 false) |
| `LOOP_INTERVAL` | `600` | [可选] 循环模式下的轮询间隔（秒） |

### 第四步：启用自动化
1. 开启仓库的 **Workflow permissions** (Read and write)。
2. 在 **Actions** 标签页中手动运行一次 `Update Nitter Instances`。
3. 随后运行 `Twitter Monitor` 即可。

## ⚙️ 架构说明
*   **多源并发抓取**: 程序会根据 `instances.json` 中的健康实例列表，自动尝试多点抓取，极大提高了稳定性。
*   **状态本地化**: 使用 `last_id.json` 记录每个用户的最后推送 ID，防止重复推送。

## ❓ 常见问题
**Q: 为什么图片显示异常？**
A: 本项目已支持最新的 hex URL 还原。如果仍不显示，通常是因为原始图片链接失效或代理服务波动。

**Q: 如何在本地运行？**
A: 设置 `LOOP_MODE=true`，配置好环境变量后直接 `python twitter_monitor.py` 即可。需先安装 `playwright install chromium`。
