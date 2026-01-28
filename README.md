# Twitter (X) 智能监控机器人 🤖

这是一个基于 **Playwright Stealth** 技术的工业级推文监控方案。它通过模拟真实浏览器行为，完美绕过屏蔽与机器人检测，将 Twitter 动态（含文字、图片、转发）实时推送到您的钉钉。

本项目专为 **GitHub Actions** 设计，全自动运行，无需自备服务器。

## ✨ 核心亮点

*   **🛡️ 强力反检测**: 放弃传统的 RSS 接口，采用 **Playwright 浏览器自动化** + Stealth 插件。自动模拟人类点击，轻松穿透 Nitter 验证码与访问限制。
*   **🖼️ 完美图文展示**: 
    *   **图片代理**: 内置 `weserv.nl` 代理服务，彻底解决国内钉钉因网络问题加载不出推文配图的痛点。
    *   **Twitter 样式模拟**: 动态识别转发（Retweet）状态，在钉钉中使用引用块和视觉图标，体验原汁原味的推文内容。
*   **📡 自动发现可用节点**: 集成 `status.d420.de` API，每 6 小时自动扫描全球 Nitter 节点，动态优选最稳、最快的“黄金实例”存入本地，无需手动维护。
*   **🧠 智能过滤逻辑**: 自动识别并跳过博主的**置顶推文 (Pinned Tweets)**，确保只在发布真正的“新鲜项”时才报警。
*   **⚡ 高性能解耦架构**: 实例更新任务与监控任务物理分离。主程序启动即从本地缓存读取节点，运行速度极快。

## 🚀 部署指南

### 第一步：代码就绪
确保您的 GitHub 仓库根目录中包含以下核心文件：
```text
repo-root/
├── .github/workflows/
│   ├── main.yml             (主监控：每 10 分钟运行一次)
│   └── update_instances.yml (实例同步：每 6 小时运行一次)
├── twitter_monitor.py       (核心抓取与推送程序)
├── update_instances.py      (实例自动化发现工具)
├── requirements.txt         (支持 Playwright & BeautifulSoup)
└── README.md
```

### 第二步：配置钉钉机器人
1. 钉钉群组 -> 设置 -> 智能群助手 -> 添加机器人 -> 自定义。
2. **安全设置**：选择“自定义关键词”，填入：`Twitter`。
3. 复制生成的 Webhook URL。

### 第三步：设置 GitHub Secrets
在 GitHub 仓库 **Settings -> Secrets and variables -> Actions** 中添加：

| Secret Name | 示例 Value | 说明 |
|-------------|------------|------|
| `TWITTER_USER` | `elonmusk` 或 `search:关键词` | 监控目标。**多个请用英文逗号分隔**。 |
| `DINGTALK_WEBHOOK` | `https://oapi.dingtalk.com/...` | 钉钉机器人 Webhook 地址 |

### 第四步：启用自动化
1. 确保仓库 **Settings -> Actions -> General** 中的 `Workflow permissions` 开启了 **Read and write permissions**。
2. 在 **Actions** 标签页中手动运行一次 `Update Nitter Instances`（获取首条实例列表数据）。
3. 随后运行 `Twitter Monitor` 即可。

## ⚙️ 架构说明
*   **双流水线**: 
    *   `Update Nitter Instances`: 定时从状态页同步健康实例，并自动提交到仓库。
    *   `Twitter Monitor`: 基于 `playwright-python` 渲染后提取 HTML 内容，完成抓取与推送。

## ❓ 常见问题
**Q: 为什么推文里的图片加载不出来？**
A: 本项目已内置图片透明代理。如果仍有极个别图片显示异常，通常是由于原始 Nitter 节点暂时不可访问。

**Q: 频率可以调快吗？**
A: 可以修改 `main.yml` 中的 `cron` 字段。建议不快于 10 分钟，以维持 GitHub 的正常配额。
