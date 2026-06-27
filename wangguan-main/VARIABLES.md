# 📋 环境变量完整清单

本文档列出「通用 MCP 网关」**所有**支持的环境变量，按子系统分组。每项标注是否必填、默认值、来源代码与说明。

> - 标注 **【必填】**：缺失会导致对应功能无法启动。
> - 标注 **【可选】**：留空即自动禁用该功能，网关会优雅降级。
> - 兼容旧变量名（向后兼容）在「兼容别名」列注明。

---

## 目录
- [1. 基础部署](#1-基础部署)
- [2. 数据库 (Supabase)](#2-数据库-supabase)
- [3. 多模型 LLM](#3-多模型-llm)
- [4. 向量记忆 (Mem0 + Pinecone)](#4-向量记忆-mem0--pinecone)
- [5. 通讯渠道](#5-通讯渠道)
- [6. Google 集成](#6-google-集成)
- [7. 地图 / GPS](#7-地图--gps)
- [8. 多媒体生成](#8-多媒体生成)
- [9. 网页搜索](#9-网页搜索)
- [10. 云端笔记 (WebDAV)](#10-云端笔记-webdav)
- [11. NapCat QQ 接入](#11-napcat-qq-接入)
- [12. 后台心跳调度](#12-后台心跳调度)
- [13. 其他可选](#13-其他可选)
- [最小可运行配置示例](#最小可运行配置示例)

---

## 1. 基础部署

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `PORT` | ✅ | `10000` | 网关监听端口（Dockerfile `EXPOSE 10000`） |
| `GATEWAY_HOST` | ❌ | `localhost:8000` | 反代场景下修正的 Host 头，一般留空 |
| `API_SECRET` | ✅ | 空 | `/api/*` 管理接口的安全密钥，防止未授权调用 |
| `LOG_FILE` | ❌ | 空 | 日志文件路径（供 `/api/logs` 读取，留空则用平台日志） |
| `RESTART_WEBHOOK_URL` | ❌ | 空 | 云平台重启回调 URL（供 `/api/restart` 调用） |

### 1.1 🧠 智能体身份（控制 `/v1/chat/completions` 的人格化行为）

仅当配置了 `SUPABASE_URL` 时生效（启用上文注入 + 存库）。不配则纯透传。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `USER_NAME` | ❌ | `用户` | 用户称呼，注入到 system 提示与存库记录（如 `张三`） |
| `AI_NAME` | ❌ | `助手` | AI 角色称呼，注入到 system 提示与存库记录（如 `小橘`） |
| `USER_ID` | ❌ | `default` | 用户隔离 ID（Mem0 向量记忆按此区分不同用户） |
| `AI_PERSONA` | ❌ | 空 | AI 人设完整文本，会拼接到 system 提示最前面 |
| `CHAT_TAG` | ❌ | `Web_Chat` | 存库时给本轮对话打的标签（用于区分网页/TG/QQ 渠道） |
| `SUMMARY_THRESHOLD` | ❌ | `30` | 🆕 自动总结阈值：全渠道（网页/QQ/TG/邮件）对话流水累计达到该条数时，自动调用聊天模型（`main_chat`）生成第一人称阶段总结，存入 `Core_Cognition` 并归档旧记录。依赖 `CHAT_API_KEY`。 |

---

## 2. 数据库 (Supabase)

记忆、画像、提醒、记忆小屋、记账、设备定位等持久化所需。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `SUPABASE_URL` | ✅ | 空 | Supabase 项目 URL，如 `https://xxxxx.supabase.co` |
| `SUPABASE_KEY` | ✅ | 空 | Supabase service_role key（生产推荐）或 anon key |

> 建表 SQL 见 `DEPLOY_ZEABUR.md` 附录。

---

## 3. 多模型 LLM

网关支持 5 个 LLM 角色，用 `switch_ai_brain` 工具可热切换默认角色。最小化配置只需 `OPENAI_*`。

### 3.1 默认 / 通用模型 (OpenAI 兼容) ⚠️ 已废弃

> ⚠️ **自 v2.0 起，系统不再主动调用此模型**。所有对话/总结/日记已统一改用 `main_chat`（见 3.2）。
> 本组变量仅作**向后兼容保留**：若 `main_chat` 未配置，极少数回退逻辑（如 `_ask_llm_async` 的模型名兜底）仍会读取它。
> **推荐：直接配置 `CHAT_*` 即可，无需配置本组。**

| 变量名 | 必填 | 默认值 | 兼容别名 |
|--------|:---:|--------|---------|
| `OPENAI_API_KEY` | ❌ | 空 | `DEFAULT_API_KEY` |
| `OPENAI_BASE_URL` | ❌ | 空（用官方） | `DEFAULT_BASE_URL` |
| `OPENAI_MODEL_NAME` | ❌ | `gpt-3.5-turbo` | `DEFAULT_MODEL_NAME` |

> 支持任何 OpenAI 兼容服务：OpenAI / DeepSeek / 通义千问 / 硅基流动 / 自建 vLLM。第三方需配置 `OPENAI_BASE_URL`。

### 3.2 主对话模型 CHAT (日常聊天主力)

可被数据库 `user_facts` 表 `key='llm_settings'` 的 JSON 动态覆盖。

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `CHAT_API_KEY` | ❌ | 空 |
| `CHAT_BASE_URL` | ❌ | `https://api.minimaxi.com/v1` |
| `CHAT_MODEL_NAME` | ❌ | `abab6.5s-chat` |

### 3.3 硅基流动 SILICON1 (便宜模型)

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `SILICON1_API_KEY` | ❌ | 空 |
| `SILICON1_BASE_URL` | ❌ | `https://api.siliconflow.cn/v1` |
| `SILICON1_MODEL_NAME` | ❌ | `Qwen/Qwen2.5-7B-Instruct` |

### 3.4 视觉模型 VISION (图片识别 / OCR)

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `VISION_API_KEY` | ❌ | 空 |
| `VISION_BASE_URL` | ❌ | 空 |
| `VISION_MODEL_NAME` | ❌ | `gpt-4o-mini` |

### 3.5 语音模型 VOICE (STT 语音转文字)

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `VOICE_API_KEY` | ❌ | 回退到 `OPENAI_API_KEY` |
| `VOICE_BASE_URL` | ❌ | `https://api.openai.com/v1` |

### 3.6 向量嵌入 (Doubao / 硅基流动)

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `DOUBAO_API_KEY` | ❌ | 空 |
| `DOUBAO_EMBEDDING_EP` | ❌ | 空（如 `BAAI/bge-m3`） |

### 3.7 AI 人设

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `AI_PERSONA` | ❌ | `你是一个通用智能助手。` |

---

## 4. 向量记忆 (Mem0 + Pinecone)

启用后，记忆会在 Mem0（主）和 Pinecone（兜底）双写，保证不丢，并支持语义检索。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `MEM0_API_KEY` | ❌ | 空 | Mem0 云服务 Token |
| `MEM0_USER_ID` | ❌ | `default` | 用户隔离 ID（区分不同用户记忆） |
| `PINECONE_API_KEY` | ❌ | 空 | Pinecone 向量库 Key（兜底） |
| `PINECONE_INDEX_NAME` | ❌ | `notion-brain-v2` | Pinecone 索引名 |

---

## 5. 通讯渠道

### 5.1 Telegram

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `TG_BOT_TOKEN` | ❌ | 空 | Telegram Bot Token |
| `TG_CHAT_ID` | ❌ | 空 | 默认推送目标（私聊 ID） |
| `TG_GROUP_ID` | ❌ | 空 | 群组 ID（可选） |

### 5.2 邮件 (Resend)

| 变量名 | 必填 | 默认值 | 兼容别名 |
|--------|:---:|--------|---------|
| `RESEND_API_KEY` | ❌ | 空 | — |
| `MY_EMAIL` | ❌ | 空 | `ADMIN_EMAIL` |
| `GMAIL_BRIDGE_URL` | ❌ | 空 | Gmail 桥接地址（供信箱巡视器轮询） |

---

## 6. Google 集成

Gmail 收发 & Google 日历。需要 Google OAuth 用户令牌。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `GOOGLE_USER_TOKEN_JSON` | ❌ | 空 | OAuth 用户令牌 JSON（序列化为单行字符串） |
| `GOOGLE_CALENDAR_ID` | ❌ | `primary` | 目标日历 ID |

> 最简单获取 `token.json` 的方式：本地用 Google 官方 [quickstart](https://developers.google.com/gmail/api/quickstart/python) 跑一次。

---

## 7. 地图 / GPS

高德地图服务，周边探索 / 天气。设备定位数据通过 Supabase 的 `device_data` 表写入。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `AMAP_API_KEY` | ❌ | 空 | [高德开放平台](https://lbs.amap.com) Web 服务 Key |

---

## 8. 多媒体生成

### 8.1 AI 音乐 / 翻唱 (Replicate)

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `REPLICATE_API_KEY` | ❌ | 空 | Replicate 官方 Token |
| `MUSIC_MODEL_VERSION` | ❌ | 空 | 原创音乐模型 version hash |
| `VOICE_MODEL_VERSION` | ❌ | 空 | RVC 翻唱音色模型 version hash |
| `MUSIC_API_KEY` | ❌ | 空 | 其他音乐生成服务 Key（可选） |
| `MUSIC_API_URL` | ❌ | 空 | 其他音乐生成服务地址（可选） |

### 8.2 HTML 转图片 (HCTI)

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `HCTI_API_ID` | ❌ | 空 |
| `HCTI_API_KEY` | ❌ | 空 |

---

## 9. 网页搜索

默认使用 DuckDuckGo 免费兜底（零配置）。配置 Tavily 后切换到高质量搜索。

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `TAVILY_API_KEY` | ❌ | 空 |

---

## 10. 云端笔记 (WebDAV)

支持坚果云等 WebDAV 服务。

| 变量名 | 必填 | 默认值 |
|--------|:---:|--------|
| `WEBDAV_URL` | ❌ | 空 |
| `WEBDAV_USER` | ❌ | 空 |
| `WEBDAV_PASSWORD` | ❌ | 空 |

---

## 11. NapCat QQ 接入

通过 [NapCat](https://github.com/NapNeko/NapCatQQ) 协议实现 QQ 机器人。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `NAPCAT_WS_URL` | ❌ | 空 | 正向 WS 地址（如 `ws://host:3001`） |
| `NAPCAT_HTTP_URL` | ❌ | 空 | HTTP 回调地址 |
| `NAPCAT_BOT_QQ` | ❌ | 空 | 机器人 QQ 号 |
| `NAPCAT_TARGET_USER` | ❌ | 空 | 限定响应的私聊用户 QQ（留空则所有人可聊） |
| `NAPCAT_NOTIFY_QQ` | ❌ | 空 | 掉线通知 QQ，多个用逗号分隔 |
| `NAPCAT_NOTIFY_TG` | ❌ | 空 | 掉线同时通知 TG（`true`/`false`） |
| `NAPCAT_ALLOWED_GROUPS` | ❌ | 空 | 允许响应的群号，逗号分隔 |
| `NAPCAT_RECONNECT_DELAY` | ❌ | `5` | 重连初始延迟（秒） |
| `NAPCAT_BACKOFF_FACTOR` | ❌ | `1.5` | 退避乘数 |
| `NAPCAT_MAX_DELAY` | ❌ | `60` | 最大重连延迟（秒） |

---

## 12. 后台心跳调度

`heartbeat.py` 的主动问候、消息总结、日程播报相关。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `HEARTBEAT_INTERVAL` | ❌ | `7200` | 主动问候间隔（秒） |
| `SUMMARIZE_INTERVAL` | ❌ | `1800` | 消息总结间隔（秒） |
| `SCHEDULE_MORNING_TIME` | ❌ | `07:30` | 日程早播时间 |
| `SCHEDULE_EVENING_TIME` | ❌ | `22:00` | 日程晚播时间 |
| `DIARY_TIME` | ❌ | `03:00` | 🆕 每日日记生成时间（24小时制）。到点自动拉取昨日全部对话流水，调用聊天模型（`main_chat`）生成第一人称"昨日回溯"日记，存入 Core_Cognition。启动时若发现昨日日记缺失会自动补写。依赖 CHAT_API_KEY。 |
| `SYNC_KEYS` | ❌ | 空 | 额外热同步的环境变量键，逗号分隔 |

---

## 13. 其他可选

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `MUTE_KEYWORDS` | ❌ | 空 | 触发静音的关键词，逗号分隔 |
| `MUTE_DURATION` | ❌ | `300` | 静音持续秒数 |
| `OCR_ENABLED` | ❌ | `false` | 是否开启 QQ 图片 OCR |
| `OCR_MAX_IMAGES` | ❌ | `3` | 单次最多识别图片数 |
| `SILICON_API_KEY` | ❌ | 空 | STT 语音识别 Key（硅基流动） |
| `SILICON_STT_BASE_URL` | ❌ | 空 | STT 服务地址 |
| `SILICON_STT_MODEL` | ❌ | 空 | STT 模型名 |
| `MINIMAX_API_KEY` | ❌ | 空 | Minimax TTS 文字转语音 Key |
| `ZEABUR_API_KEY` | ❌ | 空 | Zeabur 平台 API Token（API 触发重启） |
| `NAPCAT_PROJECT_ID` | ❌ | 空 | Zeabur 项目 ID |
| `NAPCAT_SERVICE_ID` | ❌ | 空 | Zeabur 服务 ID |

---

## 最小可运行配置示例

只配置以下 3 项，网关即可正常启动并提供基础 MCP 工具：

```env
# 必填：基础 + LLM（主对话模型 CHAT_*）
PORT=10000
API_SECRET=请改成你的随机密钥
CHAT_API_KEY=sk-xxxxxxxx
CHAT_MODEL_NAME=abab6.5s-chat
# 注：OPENAI_* 已废弃，所有对话/总结统一用 CHAT_*，无需配置

# 可选但推荐：数据库 + 推送
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGci...
TG_BOT_TOKEN=123456:ABC-DEF...
TG_CHAT_ID=123456789
AI_PERSONA=你是一个通用智能助手。
```

> 💡 其余所有变量均为可选，按需启用对应功能即可。未配置的功能会优雅降级而非报错。

---

## 变量生效与热更新

- **启动时读取**：所有变量在网关启动时读取并缓存在内存中。
- **热更新**：通过 `POST /api/config` 接口可热更新部分变量（需 `API_SECRET` 鉴权），无需重启。
- **重启生效**：修改变量后，调用 `POST /api/restart` 或在云平台重新部署即可完整生效。

> 📚 部署细节请参考 [DEPLOY_ZEABUR.md](DEPLOY_ZEABUR.md)，项目总览请参考 [README.md](README.md)。