# Twitter (X) 监控机器人 🤖

这是一个轻量级的 Python 脚本，用于监控指定 Twitter 用户的最新推文，并通过钉钉机器人（WebHook）实时推送通知。

本项目专为 **GitHub Actions** 设计，可免费实现 24/7 自动化监控，无需购买服务器。

## ✨ 功能特点

*   **无需 API Key**: 使用 Nitter 开源前端的 RSS 接口，规避 X.com 昂贵的 API 限制。
*   **智能去重**: 本地记录最后一条推送 ID，避免重复报警。
*   **多实例容灾**: 内置多个 Nitter 公共实例，自动轮询，提高稳定性。
*   **自动化运行**: 预配置 GitHub Actions，每 10 分钟自动检查一次。
*   **钉钉推送**: 支持 Markdown 格式的消息推送，美观易读。

## 🚀 部署指南

### 第一步：准备代码
将本文件夹（`x` 文件夹）内的**所有内容**移动到你的 GitHub 仓库根目录。
确保文件结构如下：
```text
repo-root/
├── .github/
│   └── workflows/
│       └── main.yml
├── twitter_monitor.py
├── requirements.txt
└── README.md
```

### 第二步：配置钉钉机器人
1. 打开钉钉群组 -> 设置 -> 智能群助手 -> 添加机器人 -> 自定义。
2. 安全设置选择 **“自定义关键词”**，填入：`Twitter` （或者 `推文`）。
3. 复制生成的 Webhook URL。

### 第三步：设置 GitHub Secrets
在你的 GitHub 仓库页面：
1. 点击 **Settings** -> **Secrets and variables** -> **Actions**。
2. 点击 **New repository secret**，添加以下两个变量：

| Secret Name | Value 示例 | 说明 |
|-------------|------------|------|
| `TWITTER_USER` | `elonmusk` 或 `search:CONAN_tcg` | 支持用户名监控或关键词搜索监控（以 `search:` 开头）。**多个项请用逗号分隔**。 |
| `DINGTALK_WEBHOOK` | `https://oapi.dingtalk.com/robot/send...` | 你的钉钉机器人 Webhook URL |

### 第四步：启用工作流
1. 推送代码到 GitHub。
2. GitHub Actions 应该会自动开始按照 Cron 计划运行（每10分钟）。
3. 你也可以在 **Actions** 标签页中，手动点击 **Run workflow** 进行测试。

> ⚠️ **注意**：首次运行时，Actions 需要由该仓库的默认 Token 提交代码（回传 `last_id.txt`）。请确保 Settings -> Actions -> General -> Workflow permissions 中已勾选 **Read and write permissions**。

## 🛠️ 文件说明

*   `twitter_monitor.py`: 核心脚本。会读取 `last_id.txt`（自动生成）来判断是否有新推文。
*   `.github/workflows/main.yml`: 自动化配置。包含运行环境、依赖安装和自动回传 `last_id.txt` 的逻辑。

## ❓ 常见问题

**Q: 为什么有时候收不到推送？**
A: Nitter 实例有时会触发机器人验证（Bot Challenge）。新版脚本会自动识别并跳过被拦截的实例，尝试下一个健康节点。如果是“关键字搜索”任务，脚本会优先使用 RSSHub 以提高成功率。

**Q: 如何修改检查频率？**
A: 修改 `.github/workflows/main.yml` 中的 `- cron: '*/10 * * * *'` 字段。
