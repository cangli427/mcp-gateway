# 🚀 Zeabur 部署完整教程

本教程手把手教你在 [Zeabur](https://zeabur.com) 上部署「通用 MCP 网关」。Zeabur 是原版项目的诞生地，支持长驻进程、自动 HTTPS、自动识别 Dockerfile，是最省心的部署方式。

> ⏱ 预计耗时：15~30 分钟（取决于你已有多少第三方服务的 Key）

---

## 📋 目录

- [前置准备](#前置准备)
- [第 1 步：推送代码到 GitHub](#第-1-步推送代码到-github)
- [第 2 步：在 Zeabur 创建项目](#第-2-步在-zeabur-创建项目)
- [第 3 步：配置环境变量](#第-3-步配置环境变量)
- [第 4 步：绑定域名 & 暴露端口](#第-4-步绑定域名--暴露端口)
- [第 5 步：验证部署](#第-5-步验证部署)
- [第 6 步：接入 MCP 客户端](#第-6-步接入-mcp-客户端)
- [常见问题排查](#常见问题排查)
- [附录：数据库表 SQL](#附录数据库表-sql)

---

## 前置准备

在开始之前，你需要准备好以下东西：

### 必备
| 项目 | 说明 | 获取方式 |
|------|------|---------|
| **Zeabur 账号** | 可用 GitHub 登录 | [zeabur.com](https://zeabur.com) |
| **GitHub 账号** | 用于托管代码 | [github.com](https://github.com) |
| **LLM API Key** | 网关的核心大脑（OpenAI / DeepSeek / 通义等均可） | 对应平台的开发者控制台 |

### 推荐（解锁更多功能）
| 项目 | 说明 | 免费额度 |
|------|------|---------|
| **Supabase 账号** | 提供数据库（记忆/画像/提醒持久化） | ✅ 免费层 |
| **Telegram Bot Token** | 消息推送 + Telegram 轮询 | ✅ 免费 |

### 可选（按需）
| 项目 | 用途 |
|------|------|
| Mem0 / Pinecone | 长期记忆向量检索 |
| Tavily API Key | 高质量网页搜索 |
| Google OAuth Token | Gmail 收发 / Google 日历 |
| Resend API Key | 邮件发送 |
| 高德 API Key | 周边探索 / 天气 |
| Replicate API Key | AI 作曲 / 翻唱 |
| WebDAV (坚果云) | 云端笔记读写 |

> 💡 **可以先跳过可选项目**，部署成功后再逐步添加。网关会自动检测哪些服务已配置，未配置的功能会优雅降级而非报错。

---

## 第 1 步：推送代码到 GitHub

### 1.1 创建 GitHub 仓库

1. 打开 [github.com/new](https://github.com/new)
2. Repository name 填：`mcp-gateway`（或你喜欢的名字）
3. 选择 **Private**（推荐，保护你的代码）
4. ✅ 勾选 `Add a README file`
5. 点击 **Create repository**

### 1.2 推送本地代码

在本项目目录下打开终端：

```bash
# 初始化 Git 仓库（如果还没有的话）
git init

# 添加远程仓库（替换成你的地址）
git remote add origin https://github.com/<你的用户名>/mcp-gateway.git

# 添加所有文件
git add -A

# 提交
git commit -m "Initial commit: Generic MCP Gateway"

# 推送到 GitHub
git branch -M main
git push -u origin main
```

> ⚠️ **安全提醒**：推送前请确认已排除 `.env` 文件（本仓库的 `.dockerignore` 已包含），避免泄露密钥。

---

## 第 2 步：在 Zeabur 创建项目

### 2.1 新建项目

1. 登录 [Zeabur Dashboard](https://dashboard.zeabur.com)
2. 点击 **+ New Project**（新建项目）
3. 项目名填：`mcp-gateway`，选择一个离你较近的区域（如 `Asia - Hong Kong`）
4. 点击 **Create**

### 2.2 添加 Service（服务）

1. 在项目页面点击 **+ Add Service**
2. 选择 **Git Repository**
3. 授权 Zeabur 访问你的 GitHub（首次需要）
4. 选择刚才推送的 `mcp-gateway` 仓库

### 2.3 确认构建配置

Zeabur 会自动检测到项目根目录的 `Dockerfile`，通常**无需手动配置**：

| 配置项 | 预期值 | 说明 |
|--------|--------|------|
| Build Type | `Dockerfile` | 自动识别 ✅ |
| Dockerfile Path | `./Dockerfile` | 默认 ✅ |
| Start Command | （Dockerfile 内的 `CMD`） | 无需填写 ✅ |
| Port | `10000` | 见第 4 步设置 |

> 💡 如果 Zeabur 没有自动识别 Dockerfile，手动在 **Settings → Build** 里把 Build Type 改为 `Dockerfile`。

### 2.4 等待首次构建

点击 **Deploy** 后，Zeabur 会开始拉取代码并构建 Docker 镜像。

- 构建过程：拉取 `python:3.11-slim` → 安装依赖 → 复制源码
- 预计耗时：**2~5 分钟**（首次较慢，后续有缓存会快很多）
- 构建成功后，状态会变为绿色 **Running**

> ⚠️ 此刻服务虽然跑起来了，但**还没配置环境变量**，功能不可用。请继续下一步。

---

## 第 3 步：配置环境变量

这是**最关键的一步**。在 Zeabur 的 Service 详情页，找到 **Variables**（环境变量）标签页。

### 3.1 🔴 必填项（最小可运行配置）

至少配置以下 2 项，网关才能正常启动并提供基础 MCP 工具：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `OPENAI_API_KEY` | `sk-xxxxxxxx` | 你的 LLM API Key（兼容 OpenAI / DeepSeek / 通义 / vLLM 等） |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` | 模型名称 |

如果你用的是 **OpenAI 兼容的第三方服务**（如 DeepSeek、通义千问、自建 vLLM），还需额外配置 Base URL：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `OPENAI_BASE_URL` | `https://api.deepseek.com/v1` | 第三方服务的 API 地址（注意要带 `/v1`） |

> 💡 代码内部仍兼容旧的 `DEFAULT_API_KEY` / `DEFAULT_MODEL_NAME` / `DEFAULT_BASE_URL` 变量名，但推荐使用新的 `OPENAI_*` 命名。
>
> 配好这 2~3 项后，**重新部署**一次，网关就能正常工作了。以下为可选增强。

#### 🔐 接口安全密钥（强烈建议配置）

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `API_SECRET` | `你自定义的一串随机字符串` | 所有 `/api/*` 管理接口的鉴权密钥，防止未授权调用 |

> ⚠️ 不配置 `API_SECRET` 的话，任何人都能通过你的域名调用 `/api/config`、`/api/restart` 等接口，存在安全风险。

### 3.2 🟡 推荐配置（解锁记忆 & 推送）

#### Supabase 数据库（记忆/画像/提醒持久化）

1. 登录 [supabase.com](https://supabase.com)，新建一个项目
2. 在项目 **Settings → API** 页面获取 URL 和 anon key
3. 在 Supabase 的 SQL Editor 中执行[附录的建表 SQL](#附录数据库表-sql)
4. 回到 Zeabur，添加以下变量：

| 变量名 | 值 |
|--------|-----|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` |
| `SUPABASE_KEY` | `eyJhbGci...`（anon key） |

#### Telegram 推送 & 轮询

1. 在 Telegram 找 [@BotFather](https://t.me/BotFather)，创建一个 Bot，获取 Token
2. 给你的 Bot 发一条消息，然后访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 获取 `chat_id`
3. 添加变量：

| 变量名 | 值 |
|--------|-----|
| `TG_BOT_TOKEN` | `123456:ABC-DEF...` |
| `TG_CHAT_ID` | `你的 chat_id` |

#### AI 人设

| 变量名 | 值 |
|--------|-----|
| `AI_PERSONA` | `你是一个通用智能助手。` |

### 3.3 🟢 可选增强（按需开启）

以下功能**默认关闭**，需要时再添加对应变量即可，无需改代码：

<details>
<summary>📧 邮件发送 (Resend)</summary>

| 变量名 | 说明 |
|--------|------|
| `RESEND_API_KEY` | [resend.com](https://resend.com) API Key |
| `MY_EMAIL` | 管理员收件邮箱（兼容旧变量 `ADMIN_EMAIL`） |

</details>

<details>
<summary>📧 Gmail 收发 & Google 日历</summary>

需要 Google OAuth 用户令牌。最简单的方式：在本地用 Google 官方 [quickstart](https://developers.google.com/gmail/api/quickstart/python) 跑一次，会生成 `token.json`，然后把整个 JSON 序列化成一行字符串。

| 变量名 | 说明 |
|--------|-----|
| `GOOGLE_USER_TOKEN_JSON` | token.json 的完整内容（单行） |
| `GOOGLE_CALENDAR_ID` | 日历 ID，默认 `primary` |

</details>

<details>
<summary>🗺️ 地图 & GPS (高德)</summary>

| 变量名 | 说明 |
|--------|-----|
| `AMAP_API_KEY` | [高德开放平台](https://lbs.amap.com) Web 服务 Key |

> 还需要在 Supabase 中创建 `device_data` 表接收定位数据（见附录），网关才能读取位置。

</details>

<details>
<summary>🎵 AI 音乐 (Replicate)</summary>

| 变量名 | 说明 |
|--------|-----|
| `REPLICATE_API_KEY` | [replicate.com](https://replicate.com) Token |
| `MUSIC_MODEL_VERSION` | 原创音乐模型 version hash |
| `VOICE_MODEL_VERSION` | RVC 翻唱模型 version hash |

</details>

<details>
<summary>📝 云端笔记 (WebDAV / 坚果云)</summary>

| 变量名 | 说明 |
|--------|-----|
| `WEBDAV_URL` | WebDAV 根目录，如坚果云的 `https://dav.jianguoyun.com/dav/` |
| `WEBDAV_USER` | 用户名 |
| `WEBDAV_PASSWORD` | 应用专用密码 |

</details>

<details>
<summary>🖼️ HTML 转图片 (HCTI)</summary>

| 变量名 | 说明 |
|--------|-----|
| `HCTI_API_ID` | [htmlcsstoimage](https://htmlcsstoimage.com) ID |
| `HCTI_API_KEY` | 对应 Key |

</details>

<details>
<summary>🧠 长期记忆 (Mem0 + Pinecone 双写)</summary>

启用后，记忆会在 Mem0（主）和 Pinecone（兜底）双写，保证不丢，并支持语义检索。

| 变量名 | 说明 |
|--------|------|
| `MEM0_API_KEY` | [mem0.ai](https://mem0.ai) API Key |
| `MEM0_USER_ID` | 用户标识，默认 `default` |
| `PINECONE_API_KEY` | [pinecone.io](https://pinecone.io) API Key（兜底向量库） |
| `PINECONE_INDEX_NAME` | Pinecone 索引名，默认 `notion-brain-v2` |
| `DOUBAO_API_KEY` | 向量嵌入用 Key（兼容变量，默认走硅基流动 embedding） |
| `DOUBAO_EMBEDDING_EP` | 嵌入模型名，如 `BAAI/bge-m3` |

</details>

<details>
<summary>🔍 高质量网页搜索 (Tavily)</summary>

默认使用 DuckDuckGo 免费兜底（零配置）。配置 Tavily 后切换到高质量搜索。

| 变量名 | 说明 |
|--------|------|
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) API Key |

</details>

<details>
<summary>🤖 多 LLM 角色 (按需启用)</summary>

网关支持 5 个 LLM 角色按用途隔离，用 `switch_ai_brain` 工具可热切换默认角色。最小化配置只需 `OPENAI_*`。

| 变量前缀 | 用途 | 对应变量（前缀 + `_API_KEY` / `_BASE_URL` / `_MODEL_NAME`） |
|----------|------|-------------------------------------------------------------|
| `OPENAI_` | 默认通用模型 | `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL_NAME` |
| `CHAT_` | 主对话模型（可数据库动态覆盖） | `CHAT_API_KEY` / `CHAT_BASE_URL` / `CHAT_MODEL_NAME` |
| `SILICON1_` | 硅基流动便宜模型 | `SILICON1_API_KEY` / `SILICON1_BASE_URL` / `SILICON1_MODEL_NAME` |
| `VISION_` | 视觉 / OCR 模型 | `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL_NAME` |
| `VOICE_` | 语音 / STT 模型（回退 OPENAI） | `VOICE_API_KEY` / `VOICE_BASE_URL` / `VOICE_MODEL_NAME` |

> 💡 `CHAT_*` 支持在数据库 `user_facts` 表的 `key='llm_settings'` 中用 JSON 动态覆盖，便于运行时切换主模型。

</details>

### 3.4 在 Zeabur 批量添加变量的技巧

Zeabur 的 Variables 编辑器支持**批量粘贴**（Bulk Edit / RAW 编辑器），你可以一次性粘贴多行：

```
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_MODEL_NAME=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
API_SECRET=请改成你的随机密钥
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGci...
TG_BOT_TOKEN=123456:ABC-DEF...
TG_CHAT_ID=123456789
AI_PERSONA=你是一个通用智能助手。
```

粘贴后点击 **Save / Restart**，Zeabur 会自动重新部署并应用新变量。

### 3.5 QQ 机器人配置（可选）

如果你想接入 QQ（通过 NapCat），需要额外配置：

```
NAPCAT_WS_URL=ws://你的NapCat服务器:3001
NAPCAT_BOT_QQ=机器人的QQ号
NAPCAT_TARGET_USER=限定响应的用户QQ
```

> 详细说明见 [NapCat](https://github.com/NapNeko/NapCatQQ) 项目。这部分较复杂，建议先跑通基础功能再接入。

---

## 第 4 步：绑定域名 & 暴露端口

### 4.1 添加 Domain（域名）

1. 在 Service 详情页，切换到 **Networking** 标签
2. 点击 **Generate Domain**（生成域名）
3. Zeabur 会分配一个形如 `mcp-gateway-xxx.zeabur.app` 的免费 HTTPS 域名

> 💡 如果你有自己的域名，也可以点击 **Custom Domain** 绑定，按提示添加 CNAME 记录即可。

### 4.2 确认端口设置

| 设置项 | 值 |
|--------|-----|
| Port | `10000` |

Zeabur 通常会自动读取 Dockerfile 里的 `EXPOSE 10000`，但请务必在 **Networking** 里确认端口已正确暴露。

> ⚠️ 如果 Zeabur 没有自动识别端口，手动添加一个 Port = `10000` 的暴露规则。

### 4.3 理解路径

部署完成后，你的网关有以下访问入口：

| 路径 | 用途 |
|------|------|
| `https://mcp-gateway-xxx.zeabur.app/health` | 健康检查 |
| `https://mcp-gateway-xxx.zeabur.app/sse` | **MCP 客户端接入点** |
| `https://mcp-gateway-xxx.zeabur.app/api/config` | 配置热更新（POST） |
| `https://mcp-gateway-xxx.zeabur.app/api/logs` | 查看日志 |

---

## 第 5 步：验证部署

### 5.1 健康检查

在浏览器或终端访问：

```bash
curl https://mcp-gateway-xxx.zeabur.app/health
```

预期返回类似：

```json
{"status": "ok", "service": "GenericGateway"}
```

### 5.2 查看启动日志（配置体检报告）

在 Zeabur 的 **Runtime / Logs** 标签页，你会看到网关启动时自动打印的「配置体检报告」：

```
╔════════════════════════════════════════╗
║          🔍 配置体检报告                ║
╠════════════════════════════════════════╣
║ ✅ LLM (默认模型)    → gpt-4o-mini      ║
║ ✅ 数据库 (Supabase) → 已连接           ║
║ ❌ 长期记忆 (Mem0)   → 未配置           ║
║ ✅ Telegram 推送     → 已配置           ║
║ ❌ Gmail/日历        → 未配置 OAuth     ║
║ ❌ 邮件发送 (Resend) → 未配置           ║
║ ❌ QQ 机器人 (NapCat)→ 未配置           ║
║ ✅ 地图/GPS (高德)   → 已配置           ║
║ ✅ 网页搜索 (DDG)    → 免费免配置       ║
║ ❌ AI 音乐 (Replicate)→ 未配置          ║
║ ❌ 云端笔记 (WebDAV) → 未配置           ║
║ ❌ HTML 转图 (HCTI)  → 未配置           ║
╠════════════════════════════════════════╣
║   已启用 4/11 项功能，网关正常运行中     ║
╚════════════════════════════════════════╝
```

✅ 标记的表示该功能已就绪，❌ 标记的表示对应环境变量未配置。**这是排查「为什么某功能不工作」的第一现场。**

### 5.3 测试 MCP 工具

在终端用 `curl` 直接测试 `/sse` 是否可连通：

```bash
curl -N https://mcp-gateway-xxx.zeabur.app/sse
```

如果看到类似 `event: endpoint` 的流式输出，说明 SSE 通道正常。

---

## 第 6 步：接入 MCP 客户端

### 6.1 Claude Desktop

编辑配置文件：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "generic-gateway": {
      "url": "https://mcp-gateway-xxx.zeabur.app/sse"
    }
  }
}
```

保存后重启 Claude Desktop，在对话框输入 `帮我用 echo 工具测试一下`，如果 AI 成功调用 `echo` 工具并返回结果，说明接入成功！

### 6.2 Cursor

在 Cursor 的 **Settings → MCP** 中添加：

| 字段 | 值 |
|------|-----|
| Name | `Generic Gateway` |
| URL | `https://mcp-gateway-xxx.zeabur.app/sse` |

### 6.3 通用 MCP 客户端

任何支持 MCP 协议的客户端，只需把接入 URL 指向：

```
https://mcp-gateway-xxx.zeabur.app/sse
```

---

## 常见问题排查

### ❓ 构建失败 (Build Failed)

| 现象 | 原因 | 解决 |
|------|------|------|
| `pip install` 超时 | Zeabur 构建节点网络问题 | 重新触发部署；或在 Dockerfile 里加国内镜像源 |
| `ModuleNotFoundError` | requirements.txt 缺包 | 检查 `requirements.txt` 是否完整推送到了 GitHub |
| `Dockerfile not found` | Zeabur 没识别到 | 在 Settings → Build 手动指定 Build Type = Dockerfile |

### ❓ 部署后立即 Crash / Restart 循环

| 现象 | 原因 | 解决 |
|------|------|------|
| 容器反复重启 | 代码启动即报错 | 查看 Runtime Logs，通常是环境变量缺失导致 |
| 端口监听失败 | `PORT` 被覆盖成错误值 | 确认 Zeabur 没有注入冲突的 `PORT` 变量，代码默认用 `10000` |

### ❓ /health 返回正常，但 MCP 客户端连上后卡住

这是 **SSE 流式响应被缓冲**导致的。Zeabur 原生支持 SSE 流式（原版项目就是跑在 Zeabur 上的），一般不会出现。如果遇到：

1. 确认你的域名是 HTTPS（`https://` 开头）
2. 检查是否有自定义反代/CDN 在中间加了 buffering

### ❓ Supabase 报权限错误

Supabase 默认开启 RLS（行级安全）。两种解法：

- **方案 A（开发期推荐）**：在 Supabase 的 SQL Editor 里对每张表执行 `ALTER TABLE <表名> DISABLE ROW LEVEL SECURITY;`
- **方案 B（生产推荐）**：使用 `service_role` key 而非 anon key 作为 `SUPABASE_KEY`（注意保密）

### ❓ 时区不对 / 提醒不触发

本项目的 Dockerfile 已内置 `TZ=Asia/Shanghai`，Zeabur 上无需额外配置。如果你自行魔改了 Dockerfile，请确保保留：

```dockerfile
ENV TZ=Asia/Shanghai
```

### ❓ Telegram 不推送

1. 确认 `TG_BOT_TOKEN` 和 `TG_CHAT_ID` 都已配置（缺一不可）
2. 确认你**先给 Bot 发过消息**，否则 Bot 无法主动给你发消息（Telegram 的隐私机制）
3. 在 Logs 里搜索 `推送失败`，看具体报错

### ❓ 修改了环境变量后没生效

Zeabur 修改 Variables 后会**自动重新部署**。如果没有：
1. 手动点击 **Redeploy**
2. 或调用管理 API：`POST https://mcp-gateway-xxx.zeabur.app/api/restart`

### ❓ 如何查看实时日志

Zeabur Dashboard → 你的 Service → **Runtime** 标签 → **Logs**。所有 `print()` 输出都会出现在这里，包括网关启动时的「配置体检报告」。

---

## 附录：数据库表 SQL

在 Supabase 的 **SQL Editor** 中执行以下语句，创建网关所需的全部表：

```sql
-- ==========================================
-- 通用 MCP 网关数据库表结构
-- ==========================================

-- 1. 记忆表（核心）
create table if not exists memories (
  id bigint generated always as identity primary key,
  title text,
  content text,
  category text default '流水',          -- 流水/记事/灵感/情感/画像
  mood text default '平静',
  tags text default 'System',
  importance int default 1,              -- 权重 1~10，按 category 自动计算
  created_at text
);

-- 2. 用户画像表
create table if not exists user_facts (
  key text primary key,
  value text,
  confidence float default 1.0
);

-- 3. 提醒表
create table if not exists reminders (
  id text primary key,
  time_str text,
  content text,
  is_repeat boolean default false,
  is_paused boolean default false,
  last_fired text default ''
);

-- 4. 记忆小屋表（AI 虚拟生活系统，可选）
create table if not exists memory_house (
  id bigint generated always as identity primary key,
  room text,
  action_type text,
  content text,
  is_locked boolean default false,
  created_at text
);

-- 5. 记账表（可选）
create table if not exists expenses (
  id bigint generated always as identity primary key,
  item text,
  amount float,
  type text,
  date date
);

-- 6. 设备定位数据表（可选，供位置相关工具使用）
create table if not exists device_data (
  id bigint generated always as identity primary key,
  timestamp text,
  location_latitude float,
  location_longitude float,
  location_address text,
  foreground_app text,
  app_usage jsonb
);

-- 关闭 RLS（开发期简化配置，生产环境建议用 service_role key）
alter table memories disable row level security;
alter table user_facts disable row level security;
alter table reminders disable row level security;
alter table memory_house disable row level security;
alter table expenses disable row level security;
alter table device_data disable row level security;
```

执行完成后，回到 Zeabur 的环境变量确认 `SUPABASE_URL` 和 `SUPABASE_KEY` 已填入，重新部署即可。

---

## 🎉 完成！

部署成功后，你拥有了一个：

- ✅ 24 小时在线的 MCP 工具网关
- ✅ 自动 HTTPS 的访问域名
- ✅ 30+ 个可调用的 AI 工具
- ✅ 带记忆、画像、提醒的智能体后端
- ✅ 多渠道消息接入（Telegram / QQ）

有任何问题，优先查看 Zeabur 的 **Runtime Logs** 和网关启动时的「配置体检报告」，90% 的问题都能在那里找到答案。

---

> 📚 更多信息请参考项目根目录的 [README.md](README.md)