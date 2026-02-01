# Twitter (X) 智能监控机器人 🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Enabled-brightgreen)](https://github.com/features/actions)
[![Cloudflare Workers](https://img.shields.io/badge/Cloudflare-Workers-orange)](https://workers.cloudflare.com/)

这是一个基于 **Playwright Stealth** 技术的工业级推文监控方案。它通过模拟真实浏览器行为,完美绕过屏蔽与机器人检测,将 Twitter 动态(含文字、图片、翻译、转发)实时推送到您的钉钉。

本项目专为 **GitHub Actions** 设计,全自动运行,无需自备服务器,同时也支持本地循环模式。

> 📖 **[快速开始指南](DEPLOYMENT.md)** | 🔧 **[Cloudflare Worker 部署教程](cloudflare-worker.js)**

## ✨ 核心亮点

*   **🛡️ 强力反检测**: 放弃传统的 RSS 接口,采用 **Playwright 浏览器自动化** + Stealth 插件。自动模拟人类点击,轻松穿透 Nitter 验证码与访问限制。
*   **🌐 自动翻译与清理**: 
    *   **一键翻译**: 集成 Google Translate (GTX) 接口,自动将推文翻译为中文,方便快速阅读。
    *   **智能清洗**: 自动识别并移除推文中的装饰性乱码(如 `€∋` 等),提供纯净的阅读体验。
*   **🖼️ 完美图文展示**: 
    *   **高级图片解析**: 内置复杂的 URL 还原逻辑,能够识别并从 Nitter 的加密/代理路径(如 `xcancel` 的 hex 编码 URL)中还原出原始 `pbs.twimg.com` 地址。
    *   **Cloudflare 图片代理**: 支持使用 Cloudflare Workers 作为图片代理,确保国内钉钉客户端能够稳定加载推文配图。
*   **📡 自动发现可用节点**: 集成实例探测逻辑,定期自动扫描全球 Nitter 节点,动态优选最稳、最快的"健康实例"。
*   **🧠 智能过滤逻辑**: 自动识别并跳过博主的**置顶推文 (Pinned Tweets)**,确保只在发布真正的"新鲜项"时才报警。
*   **⚡ 高频监控**: 每 10 分钟独立执行一次,避免传统循环任务的延迟累积问题。

## 📊 功能特性

| 特性 | 本项目 | 传统方案 |
|------|--------|---------|
| 监控频率 | 每 10 分钟 | 每小时或更长 |
| 延迟时间 | 0-5 分钟 | 30-60 分钟 |
| 图片显示 | ✅ 完美支持 | ❌ 经常失败 |
| 反检测能力 | ✅ Playwright Stealth | ⚠️ 容易被封 |
| 自动翻译 | ✅ 内置 | ❌ 不支持 |
| 服务器成本 | 💰 完全免费 | 💸 需要服务器 |
| 部署难度 | ⭐⭐ 简单 | ⭐⭐⭐⭐ 复杂 |

## 🚀 部署指南

> 💡 **提示**: 完整的图文教程请查看 [DEPLOYMENT.md](DEPLOYMENT.md)

### 第一步: Fork 本仓库

点击右上角 **Fork** 按钮,将代码复制到您的 GitHub 账号。

### 第二步: 配置钉钉机器人

1. 钉钉群组 -> 设置 -> 智能群助手 -> 添加机器人 -> 自定义。
2. **安全设置**: 选择"自定义关键词",填入: `Twitter`。
3. 复制生成的 Webhook URL。

### 第三步: 配置图片访问方案

> **为什么需要配置图片访问?** 
> Twitter 图片在国内访问受限,钉钉客户端无法直接加载。本项目提供两种解决方案:

#### 方案 1: 图床上传 (推荐)

将 Twitter 图片自动上传到 **ImgBB** 图床,国内访问非常稳定。

**优点:**
- ✅ 无需自己部署服务
- ✅ 国内访问速度快
- ✅ 上传失败会自动降级到代理服务

**要求:**
- 需要在 GitHub Secrets 中配置 `IMGBB_API_KEY` (访问 [api.imgbb.com](https://api.imgbb.com/) 免费获取)。

#### 方案 2: Cloudflare Workers 代理 (可选)

如果你不想使用图床,可以部署 Cloudflare Workers 代理:

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **Workers & Pages** → **Create Worker**
3. 复制 `cloudflare-worker.js` 的内容并粘贴
4. 点击 **Deploy** 部署

### 第四步: 设置 GitHub Secrets

在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中添加:

| Secret Name | 示例 Value | 说明 |
|-------------|------------|------|
| `TWITTER_USER` | `elonmusk` | 监控目标, 多个用逗号隔开 |
| `DINGTALK_WEBHOOK` | `https://oapi...` | 钉钉机器人 Webhook |
| `IMGBB_API_KEY` | `your-imgbb-key` | **[重要]** ImgBB 的 API Key |
| `USE_IMAGE_BED` | `true` | 是否启用图床 (默认 true) |
| `CLOUDFLARE_PROXY` | `https://...` | [可选] 代理地址 |


### 第五步: 启用自动化

1. 进入仓库 **Settings → Actions → General**
2. 设置 **Workflow permissions** 为 `Read and write permissions`
3. 在 **Actions** 标签页中:
   - 手动运行一次 `Update Nitter Instances`
   - 手动运行一次 `Twitter Monitor` 测试

## ⚙️ 架构说明

### 调度策略

*   **主监控任务**: 每 10 分钟独立执行一次(标准 GitHub Actions cron)
*   **实例更新任务**: 每 6 小时更新一次健康的 Nitter 实例列表
*   **优势**: 避免长时间循环任务的延迟累积,每次执行快速且独立


### 图片访问流程

```
方案 1 (默认): Twitter 图片 → 下载 → 上传到图床 → 钉钉客户端
                                  (国内可访问)

方案 2 (备用): Twitter 图片 → Cloudflare Worker/wsrv.nl → 钉钉客户端
                              (代理服务)
```

**智能降级策略:**
1. 优先尝试上传到 ImgBB 图床
2. 如果图床失败,自动降级到 Cloudflare Worker 代理
3. 如果未配置代理,最终降级到 wsrv.nl 公共代理

### 状态管理

*   `last_id.json`: 记录每个用户的最后推送 ID,防止重复推送
*   `instances.json`: 缓存健康的 Nitter 实例列表

## 🔒 隐私声明

本项目:
- ✅ **不收集任何个人数据**
- ✅ **所有配置通过环境变量管理**
- ✅ **代码完全开源透明**
- ⚠️ **请勿监控他人私密账号**
- ⚠️ **遵守 Twitter 服务条款**

## ❓ 常见问题

**Q: 为什么图片显示异常?**  
A: 默认使用图床上传,无需额外配置。如果图床失败,会自动降级到代理服务。你可以通过设置 `USE_IMAGE_BED=false` 禁用图床,直接使用代理。

**Q: 图床服务需要注册吗?**  
A: ImgBB 需要免费注册获取 API Key。访问 [api.imgbb.com](https://api.imgbb.com/) 即可快速注册。

**Q: 如何获取 ImgBB API Key?**  
A: 
1. 访问 https://api.imgbb.com/
2. 点击 "Get API Key" 免费注册
3. 复制生成的 API Key 到 GitHub Secrets 的 `IMGBB_API_KEY`

**Q: GitHub Actions 免费额度够用吗?**  
A: 完全够用!公开仓库无限免费,私有仓库每月 2000 分钟。每次执行约 3-5 分钟,每天 144 次,公开仓库完全免费。

**Q: 如何在本地运行?**  
A: 设置环境变量后运行:
```bash
export TWITTER_USER="elonmusk"
export DINGTALK_WEBHOOK="https://..."
export LOOP_MODE="true"
python twitter_monitor.py
```

**Q: 会被 Twitter 封禁吗?**  
A: 风险极低。我们使用 Playwright Stealth 模拟真实浏览器,且每次请求间隔 10 分钟,使用多个 Nitter 实例轮换。

## 📝 更新日志

### v2.1 (2026-02)
- ✨ 新增 ImgBB 图床上传功能
- ✨ 智能降级策略:图床 → 代理 → 公共代理
- 🎯 默认启用图床,提升国内访问稳定性
- 🌐 完美解决国内图片访问问题

### v2.0 (2026-02)
- ✨ 改用标准 GitHub Actions 调度,解决延迟问题
- ✨ 支持 Cloudflare Workers 图片代理
- ✨ 添加依赖缓存,加速执行
- 🐛 修复图片显示问题

### v1.0 (2026-01)
- 🎉 初始版本发布

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

## 🙏 致谢

- [Playwright](https://playwright.dev/) - 浏览器自动化框架
- [Nitter](https://github.com/zedeus/nitter) - Twitter 前端替代品
- [Cloudflare Workers](https://workers.cloudflare.com/) - 边缘计算平台
