"""
通用 NapCat QQ 机器人模块 (Generic NapCat QQ Bot Module)
=========================================================
负责：
- 接收本地 NapCat 通过反向 WebSocket 推送的 QQ 消息
- 转发给 LLM 处理后将回复发送回 QQ
- 维护连接状态 / 登录二维码
- 自动重连与掉线通知

所有敏感配置 (QQ 号 / WS 地址 / 通知列表) 均从环境变量读取。
"""

import os
import re
import json
import time
import asyncio
import datetime

# 可选依赖：websockets
try:
    import websockets
except ImportError:
    websockets = None

# 可选依赖：requests (用于 HTTP 回调)
try:
    import requests as _requests
except ImportError:
    _requests = None


# ==========================================
# 1. 全局配置 (从环境变量读取)
# ==========================================

NAPCAT_WS_URL = os.environ.get("NAPCAT_WS_URL", "").strip()
NAPCAT_HTTP_URL = os.environ.get("NAPCAT_HTTP_URL", "").strip()
NAPCAT_BOT_QQ = os.environ.get("NAPCAT_BOT_QQ", "").strip()
NAPCAT_TARGET_USER = os.environ.get("NAPCAT_TARGET_USER", "").strip()
NAPCAT_NOTIFY_QQ = os.environ.get("NAPCAT_NOTIFY_QQ", "").strip()
NAPCAT_ALLOWED_GROUPS = os.environ.get("NAPCAT_ALLOWED_GROUPS", "").strip()

# 通知 QQ 列表
NAPCAT_NOTIFY_QQ_LIST = [x.strip() for x in NAPCAT_NOTIFY_QQ.split(",") if x.strip()]
# Telegram 通知列表 (可选，逗号分隔)
# 🗑️ [已移除] Telegram 推送通道，仅保留 QQ 通知
# NAPCAT_NOTIFY_TG_LIST = [x.strip() for x in os.environ.get("NAPCAT_NOTIFY_TG", "").split(",") if x.strip()]

# 允许响应的群列表
NAPCAT_ALLOWED_GROUPS_LIST = [x.strip() for x in NAPCAT_ALLOWED_GROUPS.split(",") if x.strip()]

# 重连参数
RECONNECT_INITIAL_DELAY = int(os.environ.get("NAPCAT_RECONNECT_DELAY", 5))
RECONNECT_BACKOFF_FACTOR = float(os.environ.get("NAPCAT_BACKOFF_FACTOR", 1.5))
RECONNECT_MAX_DELAY = int(os.environ.get("NAPCAT_MAX_DELAY", 60))


# ==========================================
# 2. 全局状态
# ==========================================

_napcat_connected = False
_napcat_ws_send = None  # 反向 WS 的 send 回调
_napcat_status_message = "未连接"
_napcat_last_connected_at = 0.0
_napcat_disconnect_count = 0
_napcat_qr_code = None
_napcat_qr_expire = 0.0
_napcat_logs = []  # 最近 200 条日志
_napcat_ws_pending = {}  # 等待响应的 WS API 请求 {echo: future}


def _naplog(msg: str):
    """记录 NapCat 模块日志。"""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _napcat_logs.append(line)
    if len(_napcat_logs) > 200:
        _napcat_logs.pop(0)
    print(line)


def _get_deps():
    """延迟获取 server 模块的依赖 (避免循环导入)。"""
    try:
        import server
        return server
    except Exception:
        return None


# ==========================================
# 3. 状态查询接口
# ==========================================

def get_napcat_status() -> dict:
    """返回当前 NapCat 连接状态汇总。"""
    return {
        "connected": _napcat_connected,
        "status_message": _napcat_status_message,
        "last_connected_at": _napcat_last_connected_at,
        "disconnect_count": _napcat_disconnect_count,
        "ws_url": NAPCAT_WS_URL or "未配置",
        "http_url": NAPCAT_HTTP_URL or "未配置",
        "bot_qq": NAPCAT_BOT_QQ,
        "target_user": NAPCAT_TARGET_USER,
        "notify_qq": NAPCAT_NOTIFY_QQ,
        "allowed_groups": NAPCAT_ALLOWED_GROUPS,
    }


def get_napcat_logs() -> list:
    """返回最近的日志列表。"""
    return _napcat_logs[-100:]


def get_napcat_qr_code() -> dict:
    """返回当前登录二维码信息 (如有效)。"""
    now = time.time()
    if _napcat_qr_code and now < _napcat_qr_expire:
        return {
            "qr_code": _napcat_qr_code,
            "remaining_seconds": int(_napcat_qr_expire - now),
        }
    return None


def _set_napcat_qr_code(qr_url):
    """设置或清除二维码缓存。"""
    global _napcat_qr_code, _napcat_qr_expire
    if qr_url:
        _napcat_qr_code = qr_url
        _napcat_qr_expire = time.time() + 300  # 默认 5 分钟有效
    else:
        _napcat_qr_code = None
        _napcat_qr_expire = 0.0


def update_napcat_config(config: dict):
    """热更新 NapCat 配置 (同时写入模块级全局变量)。"""
    global NAPCAT_WS_URL, NAPCAT_HTTP_URL, NAPCAT_BOT_QQ
    global NAPCAT_TARGET_USER, NAPCAT_NOTIFY_QQ, NAPCAT_ALLOWED_GROUPS
    global NAPCAT_NOTIFY_QQ_LIST, NAPCAT_ALLOWED_GROUPS_LIST

    if "ws_url" in config and config["ws_url"]:
        NAPCAT_WS_URL = str(config["ws_url"]).strip()
        os.environ["NAPCAT_WS_URL"] = NAPCAT_WS_URL
    if "http_url" in config and config["http_url"]:
        NAPCAT_HTTP_URL = str(config["http_url"]).strip()
        os.environ["NAPCAT_HTTP_URL"] = NAPCAT_HTTP_URL
    if "bot_qq" in config and config["bot_qq"]:
        NAPCAT_BOT_QQ = str(config["bot_qq"]).strip()
        os.environ["NAPCAT_BOT_QQ"] = NAPCAT_BOT_QQ
    if "target_user" in config and config["target_user"]:
        NAPCAT_TARGET_USER = str(config["target_user"]).strip()
        os.environ["NAPCAT_TARGET_USER"] = NAPCAT_TARGET_USER
    if "notify_qq" in config and config["notify_qq"]:
        NAPCAT_NOTIFY_QQ = str(config["notify_qq"]).strip()
        os.environ["NAPCAT_NOTIFY_QQ"] = NAPCAT_NOTIFY_QQ
        NAPCAT_NOTIFY_QQ_LIST = [x.strip() for x in NAPCAT_NOTIFY_QQ.split(",") if x.strip()]
    if "allowed_groups" in config and config["allowed_groups"]:
        NAPCAT_ALLOWED_GROUPS = str(config["allowed_groups"]).strip()
        os.environ["NAPCAT_ALLOWED_GROUPS"] = NAPCAT_ALLOWED_GROUPS
        NAPCAT_ALLOWED_GROUPS_LIST = [x.strip() for x in NAPCAT_ALLOWED_GROUPS.split(",") if x.strip()]


# ==========================================
# 4. WS API 调用 (向 NapCat 发指令)
# ==========================================

async def _call_napcat_api(action: str, params: dict = None, timeout: float = 10.0) -> dict:
    """
    通过反向 WS 向 NapCat 发送 OneBot API 请求，并等待响应。
    使用 echo 字段做请求-响应匹配。
    """
    if not _napcat_ws_send:
        _naplog(f"⚠️ WS 未连接，无法调用 API: {action}")
        return None
    echo = f"req_{int(time.time() * 1000)}_{id(params)}"
    payload = {"action": action, "params": params or {}, "echo": echo}

    fut = asyncio.get_event_loop().create_future()
    _napcat_ws_pending[echo] = fut

    try:
        await _napcat_ws_send({
            "type": "websocket.send",
            "text": json.dumps(payload)
        })
        return await asyncio.wait_for(fut, timeout=timeout)
    except Exception as e:
        _naplog(f"❌ WS API 调用失败 [{action}]: {e}")
        return None
    finally:
        _napcat_ws_pending.pop(echo, None)


async def get_qr_via_ws() -> dict:
    """通过反向 WS 获取登录二维码 / 登录状态。"""
    res = await _call_napcat_api("get_login_info")
    if res and res.get("status") == "ok":
        data = res.get("data", {})
        if data.get("user_id"):
            return {"status": "logged_in", "user_id": data["user_id"], "nickname": data.get("nickname", "")}
    # 尝试获取二维码
    res = await _call_napcat_api("get_qr_code")
    if res and res.get("status") == "ok":
        qr = res.get("data", {}).get("url") or res.get("data", {}).get("qr_code")
        if qr:
            _set_napcat_qr_code(qr)
            return {"status": "need_login", "qr_code": qr}
    return None


async def send_qq_message(user_id: int, message: str, is_group: bool = False, force_http: bool = False):
    """发送 QQ 消息。默认走反向 WS（处理消息时），force_http=True 或 WS 不可用时走 HTTP API。"""

    # 非强制 HTTP 时先尝试 WS
    if not force_http and _napcat_ws_send:
        action = "send_group_msg" if is_group else "send_private_msg"
        params = {"message": message}
        if is_group:
            params["group_id"] = user_id
        else:
            params["user_id"] = user_id
        result = await _call_napcat_api(action, params)
        if result is not None:
            return result

    # HTTP API 路径（force_http=True 或 WS 失败/不可用）
    if not NAPCAT_HTTP_URL:
        print("⚠️ [send_qq_message] 无法发送：WS 不可用且未配置 NAPCAT_HTTP_URL")
        return None

    import requests as _req
    action = "send_group_msg" if is_group else "send_private_msg"
    payload = {"message": message}
    if is_group:
        payload["group_id"] = user_id
    else:
        payload["user_id"] = user_id

    try:
        url = f"{NAPCAT_HTTP_URL.rstrip('/')}/{action}"
        print(f"📤 [send_qq_message] HTTP POST {url} | user_id={user_id}")
        resp = await asyncio.to_thread(
            lambda: _req.post(url, json=payload, timeout=15)
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ [send_qq_message] HTTP 发送成功: {data}")
            return data
        else:
            print(f"⚠️ [send_qq_message] HTTP {resp.status_code}: {resp.text[:300]}")
            return None
    except Exception as e:
        print(f"❌ [send_qq_message] HTTP 请求异常: {e}")
        return None


async def _send_disconnect_notification():
    """发送掉线通知到 QQ 和 Telegram。"""
    global _napcat_disconnect_count
    _napcat_disconnect_count += 1

    disconnect_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"⚠️ NapCat 掉线通知\n\n时间: {disconnect_time}\n断开次数: {_napcat_disconnect_count}\n请检查 NapCat 状态。"

    # QQ 通知
    if NAPCAT_NOTIFY_QQ_LIST and _requests and NAPCAT_HTTP_URL:
        for qq in NAPCAT_NOTIFY_QQ_LIST:
            try:
                url = f"{NAPCAT_HTTP_URL}/send_private_msg"
                payload = {"user_id": int(qq), "message": message}
                resp = _requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    _naplog(f"✅ 掉线通知已发送到 QQ: {qq}")
            except Exception as e:
                _naplog(f"❌ 发送 QQ 掉线通知失败: {e}")

    # 🗑️ [已移除] Telegram 掉线通知
    # 通知已通过 QQ 发送（见上方），Telegram 通道已移除。


# ==========================================
# 5.0 工具定义（OpenAI Function Calling Schema）+ 执行器
# ==========================================

NAPCAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索记忆库。当用户问还记得吗/查一下/以前之类问题时必须调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要搜索的关键词或问题"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "保存一条记忆到数据库。当用户分享重要信息、喜好、事件时需要调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "记忆标题"},
                    "content": {"type": "string", "description": "记忆内容"},
                    "category": {"type": "string", "description": "类别：记事/灵感/情感/画像/流水"}
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_diary",
            "description": "读取最近的记忆/日记/互动记录。每次对话开始时应调用，了解近期发生的事。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "获取条数，默认15"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "where_is_user",
            "description": "查询用户的实时位置、天气、当前在用App。问在哪/在干嘛时调用。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "获取用户画像/事实档案，了解用户的偏好和基本信息。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_user_fact",
            "description": "管理用户画像事实：新增或更新一条 key-value。",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "事实键名"},
                    "value": {"type": "string", "description": "事实值"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_memory_house",
            "description": "记账：记录一笔花销。",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "消费项目"},
                    "amount": {"type": "number", "description": "金额"},
                    "type": {"type": "string", "description": "类别：餐饮/购物/交通/娱乐/日常/其他"}
                },
                "required": ["item", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_expense_report",
            "description": "查询某月账单汇总。",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "月份，格式 YYYY-MM，默认当月"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_piggy_bank",
            "description": "管理虚拟储钱罐：查余额/存入/取出。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["check", "add", "spend"]},
                    "amount": {"type": "number", "description": "金额"},
                    "reason": {"type": "string", "description": "原因"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_memory_house",
            "description": "管理AI记忆小屋：在虚拟小屋里活动（看书/做饭/听音乐等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "do", "delete"]},
                    "room": {"type": "string", "description": "房间：卧室/厨房/客厅/书房/阳台"},
                    "activity": {"type": "string", "description": "活动：看书/做饭/听音乐/发呆等"},
                    "content": {"type": "string", "description": "活动内容描述"},
                    "record_id": {"type": "string", "description": "记录ID（delete时用）"}
                },
                "required": ["action"]
            }
        }
    },
]


async def _execute_tool(dep, tool_name: str, args: dict) -> str:
    """执行单个工具调用，返回结果字符串。"""
    try:
        if tool_name == "search_memory":
            return str(await dep.search_memory(query=args.get("query", "")))
        elif tool_name == "save_memory":
            return str(await dep.save_memory(
                title=args.get("title", ""),
                content=args.get("content", ""),
                category=args.get("category", "记事")
            ))
        elif tool_name == "get_latest_diary":
            limit = args.get("limit", 15)
            return str(await dep.get_latest_diary(limit=limit))
        elif tool_name == "where_is_user":
            return str(await dep.where_is_user())
        elif tool_name == "get_user_profile":
            return str(await dep.get_user_profile())
        elif tool_name == "manage_user_fact":
            return str(await dep.manage_user_fact(
                key=args.get("key", ""),
                value=args.get("value", "")
            ))
        elif tool_name == "manage_memory_house":
            return str(await dep.manage_memory_house(
                action=args.get("action", "list"),
                room=args.get("room", ""),
                activity=args.get("activity", ""),
                content=args.get("content", ""),
                record_id=args.get("record_id", "")
            ))
        # 🗑️ [已移除] 以下工具分支: web_search, manage_reminder, get_calendar_events,
        #    add_calendar_event, tarot_reading, check_inbox, list_obsidian_cloud, read_obsidian_cloud
        else:
            return f"未知工具: {tool_name}"
    except Exception as e:
        return f"工具执行出错 [{tool_name}]: {e}"
# ==========================================
# 5. 消息处理
# ==========================================

async def _process_napcat_message(data: dict, send_func):
    """【极简全能版】直接拦截并灌注所有工具结果 + 多轮对话记忆缓存"""
    global _napcat_ws_send
    
    # 基础过滤：不是用户消息就不处理
    if data.get("post_type") != "message":
        return
        
    message_type = data.get("message_type") # private 或 group
    # OneBot 格式：发送者 ID 在 sender.user_id（嵌套），不在顶层 sender_id
    sender = data.get("sender", {})
    sender_id = sender.get("user_id") or data.get("user_id")
    if sender_id is None:
        _naplog(f"⚠️ 无法解析发送者 ID，消息数据: {json.dumps(data, ensure_ascii=False)[:200]}")
        return
    raw_message = data.get("raw_message", "").strip()
    
    # 专属保护：只回复你指定的测试 QQ 号（防打扰）
    if NAPCAT_TARGET_USER and str(sender_id) != NAPCAT_TARGET_USER:
        return
        
    # 群聊被 @ 逻辑
    if message_type == "group":
        if NAPCAT_BOT_QQ and f"[CQ:at,qq={NAPCAT_BOT_QQ}]" not in raw_message:
            return
        raw_message = re.sub(r"\[CQ:at,qq=\d+\]", "", raw_message).strip()

    if not raw_message:
        return

        _naplog(f"📩 收到 QQ 消息: {raw_message}")

    try:
        dep = _get_deps()
        if not dep or not hasattr(dep, '_get_llm_client'):
            _naplog("❌ 网关核心依赖未加载")
            return

        client = dep._get_llm_client("main_chat")
        if not client:
            _naplog("❌ LLM 客户端未配置")
            return

        model_name = getattr(client, 'custom_model_name', os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash"))
        base_persona = os.getenv("AI_PERSONA", "你是一个通用智能助手。")

        # 北京时间（确保 AI 感知正确时间）
        now_bj = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
        time_context = (
            f"\n\n🕐 当前北京时间: {now_bj.strftime('%Y年%m月%d日 %H:%M')}"
            f" (星期{weekday_map[now_bj.weekday()]})"
        )

        # 工具使用指引
        tool_instruction = (
            time_context +
            "\n\n🔧 你可以调用以下真实工具（调用工具获取的数据才是事实，不是幻觉！）：\n"
            "- get_latest_diary: 读取近期记忆/日记/互动记录\n"
            "- search_memory: 搜索历史记忆（用户说「还记得吗」「查一下」时必调）\n"
            "- where_is_user: 查用户实时位置、天气、在用App\n"
            "- get_user_profile: 读取用户画像/偏好\n"
            "- save_memory: 保存重要信息到记忆库\n"
            "- manage_user_fact: 管理用户画像事实\n"
            "- save_expense / check_expense_report / manage_piggy_bank: 记账理财\n"
            "- manage_memory_house: AI小屋生活动态\n"
            "- send_email_via_api: 发送邮件\n\n"
            "⚠️ 铁律：关于记忆/事件/用户信息，必须调用工具获取真实数据，绝对不能编造！\n"
            "如果用户问「还记得吗」「之前」「查一下」，必须先调 search_memory 或 get_latest_diary！"
        )

        # 多轮对话历史缓存
        if not hasattr(_process_napcat_message, "history_cache"):
            _process_napcat_message.history_cache = {}
        cache_key = f"{message_type}_{sender_id}"
        if cache_key not in _process_napcat_message.history_cache:
            _process_napcat_message.history_cache[cache_key] = []
        history = _process_napcat_message.history_cache[cache_key]

        # 构建消息列表（system + 文本历史 + 当前消息）
        messages = [{"role": "system", "content": base_persona + tool_instruction}]
        text_history = [h for h in history if h["role"] in ("user", "assistant")]
        messages.extend(text_history[-16:])
        messages.append({"role": "user", "content": raw_message})

        # ===== Tool Calling 循环 =====
        max_tool_rounds = 5
        final_reply = None
        all_tool_results = []

        for round_idx in range(max_tool_rounds):
            _naplog(f"🔄 [QQ ToolCall] 第 {round_idx + 1} 轮 LLM 调用...")

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=NAPCAT_TOOLS,
                    tool_choice="auto",
                    temperature=0.7
                )
            )

            choice = response.choices[0]
            msg = choice.message

            # 无工具调用 → 最终文本回复
            if not msg.tool_calls:
                final_reply = msg.content
                history.append({"role": "user", "content": raw_message})
                if final_reply:
                    history.append({"role": "assistant", "content": final_reply})
                if len(history) > 20:
                    history[:] = history[-20:]
                _process_napcat_message.history_cache[cache_key] = history
                break

            # 有工具调用 → 执行每个工具
            tool_calls_data = []
            for tc in msg.tool_calls:
                tool_calls_data.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                })
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": tool_calls_data
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                _naplog(f"🔧 [QQ] 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:120]})")
                result = await _execute_tool(dep, tool_name, tool_args)
                _naplog(f"📤 [QQ] 工具返回: {str(result)[:200]}...")

                all_tool_results.append(f"[{tool_name}]: {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)
                })

            # 最后一轮强制要求回复
            if round_idx == max_tool_rounds - 1:
                messages.append({
                    "role": "user",
                    "content": "请基于以上所有工具返回的真实数据，用符合人设的口吻给我最终回复。不要再调用工具。"
                })

        # 兜底
        if not final_reply:
            history.append({"role": "user", "content": raw_message})
            final_reply = "抱歉宝贝，我脑子有点绕不过来了…待会再试试？"
            history.append({"role": "assistant", "content": final_reply})

        # 回传 QQ
        if final_reply:
            is_group = (message_type == "group")
            target_id = int(data.get("group_id")) if is_group else int(sender_id)
            await send_qq_message(target_id, final_reply, is_group=is_group)
            _naplog(f"✅ [QQ] 已回复: {final_reply[:100]}...")

        # 记忆入库（含工具调用记录）
        if dep and hasattr(dep, "_save_memory_to_db"):
            tool_info = ""
            if all_tool_results:
                tool_info = "\n\n【工具调用记录】:\n" + "\n".join(all_tool_results[-5:])
            await asyncio.to_thread(
                dep._save_memory_to_db,
                "🤖 QQ 互动",
                f"用户: {raw_message}\n回复: {final_reply}{tool_info}",
                "流水", "温柔", "QQ_MSG"
            )

        # 异步触发全渠道总结
        asyncio.create_task(check_and_summarize_all())

    except Exception as e:
        _naplog(f"❌ 处理 QQ 消息时报错: {e}")
        import traceback
        _naplog(traceback.format_exc())


# ==========================================
# 5.1 全渠道自动总结机制
# ==========================================

async def check_and_summarize_all():
    """🧠 全渠道统一对话总结机制
    统一监控所有渠道（网页/QQ/TG/邮件）的对话流水，
    当累计达到阈值（默认30条，可通过 SUMMARY_THRESHOLD 配置）时，
    自动触发大模型总结并归档，生成阶段总结存入 Core_Cognition。

    设计原则（移植自 mcp-gateway-main 并通用化）：
    - 完全变量化（AI_NAME / USER_NAME / CHAT_TAG / SUMMARY_THRESHOLD）
    - 单条消息截断 500 字，prompt 上限 8 万字，防止 token 爆炸
    - 失败兜底：即使 LLM 调用失败，也把旧记录归档，防止无限重试堆积
    - 全程 try/except 包裹，绝不影响主聊天流程
    """
    dep = _get_deps()
    if not dep:
        return
    try:
        # 配置项（全部从环境变量读取，保持通用化）
        threshold = int(os.environ.get("SUMMARY_THRESHOLD", "30"))
        ai_name = os.environ.get("AI_NAME", "助手")
        user_name = os.environ.get("USER_NAME", "用户")
        chat_tag = os.environ.get("CHAT_TAG", "Web_Chat")

        _MAX_MSG_CHARS = 500       # 每条消息最多保留500字
        _MAX_PROMPT_CHARS = 80000  # 整个prompt不超过8万字符（约2万token）

        def _check():
            if not getattr(dep, "supabase", None):
                return
            # 🌍 统一查询所有渠道的对话流水（CHAT_TAG 可配置，兼容网页/QQ/TG/邮件）
            _ALL_CHAT_TAGS = [chat_tag, "QQ_MSG", "QQ_Chat", "QQ_Group", "TG_MSG", "Email_Process"]
            all_chats = dep.supabase.table("memories").select("id, title, content, tags").in_("tags", _ALL_CHAT_TAGS).order("created_at").execute()
            if all_chats and all_chats.data and len(all_chats.data) >= threshold:
                # 只取最新的阈值条数，防止历史堆积导致token爆炸
                items_to_summarize = all_chats.data[-threshold:]
                # 将所有旧记录都归档（不仅仅是这批），防止下次再全量拉取
                all_ids_to_archive = [item['id'] for item in all_chats.data]

                _naplog(f"📦 全渠道累计对话满 {len(all_chats.data)} 条，正在触发统一总结（取最新{threshold}条，归档全部）...")

                # 逐条截断，防止单条超长消息撑爆prompt
                chat_parts = []
                total_chars = 0
                for item in items_to_summarize:
                    truncated_content = item['content'][:_MAX_MSG_CHARS]
                    tag = item.get('tags', '')
                    # 标注消息来源渠道，帮助AI理解上下文
                    channel_map = {
                        chat_tag: "网页", "QQ_MSG": "QQ", "QQ_Chat": "QQ",
                        "QQ_Group": "QQ群", "TG_MSG": "TG", "Email_Process": "邮件",
                    }
                    channel_label = channel_map.get(tag, tag)
                    part = f"[{channel_label}]{item['title']}: {truncated_content}"
                    if total_chars + len(part) > _MAX_PROMPT_CHARS:
                        _naplog(f"⚠️ 总结prompt已达 {_MAX_PROMPT_CHARS} 字符上限，截断剩余 {len(items_to_summarize) - len(chat_parts)} 条记录")
                        break
                    chat_parts.append(part)
                    total_chars += len(part)

                chat_text = "\n".join(chat_parts)
                prompt = (
                    f"以下是我们最近在各个渠道（网页/QQ/TG/邮件）的{len(chat_parts)}条对话记录：\n{chat_text}\n\n"
                    f"请你以{ai_name}(我)的第一人称视角，提取核心要点，精炼地总结一下我们最近聊了什么、发生了什么。"
                    f"⚠️严重警告：1. 必须严格区分清楚'{ai_name}(我)'做了什么，以及'{user_name}'做了什么，绝对不能把两人的话搞混！"
                    f"2. 绝对禁止以'今天'开头！因为这些聊天记录可能跨越了好几天。请扔掉日记格式，直接开门见山地叙述事情"
                    f"（例如直接说：'{user_name}最近在忙...' 或 '我们刚才聊了...'）。"
                )
                # 用户要求：总结类一律用聊天模型（main_chat），不用便宜/默认模型
                client = dep._get_llm_client("main_chat")
                if client:
                    try:
                        model_name = getattr(client, 'custom_model_name', "abab6.5s-chat")
                        summary = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.7
                        ).choices[0].message.content.strip()
                        if hasattr(dep, "_save_memory_to_db"):
                            dep._save_memory_to_db(
                                f"📚 全渠道阶段总结", summary, "记事", "温情", "Core_Cognition"
                            )
                        # 归档所有旧记录，彻底防止下次重复拉取
                        dep.supabase.table("memories").update(
                            {"tags": "Archived_Chat", "importance": 1}
                        ).in_("id", all_ids_to_archive).execute()
                        _naplog(f"✅ 全渠道对话总结完成，已归档 {len(all_ids_to_archive)} 条流水")
                    except Exception as llm_err:
                        _naplog(f"❌ 统一总结LLM调用失败: {llm_err}")
                        # 即使LLM调用失败，也把旧记录归档，防止无限重试堆积
                        dep.supabase.table("memories").update(
                            {"tags": "Archived_Chat", "importance": 1}
                        ).in_("id", all_ids_to_archive).execute()
                        _naplog(f"✅ 虽然总结失败，但已将 {len(all_ids_to_archive)} 条旧记录归档，防止下次继续堆积")
                else:
                    _naplog("⚠️ 未配置 CHAT_API_KEY，跳过总结（仅归档旧记录）")
                    dep.supabase.table("memories").update(
                        {"tags": "Archived_Chat", "importance": 1}
                    ).in_("id", all_ids_to_archive).execute()
                    _naplog(f"✅ 已将 {len(all_ids_to_archive)} 条旧记录归档")
            else:
                total_count = len(all_chats.data) if all_chats and all_chats.data else 0
                _naplog(f"📦 全渠道当前对话流水 {total_count} 条，未达{threshold}条总结阈值")
        await asyncio.to_thread(_check)
    except Exception as e:
        _naplog(f"❌ 全渠道统一总结失败: {e}")


async def _handle_poke_event(send, data, allowed_groups):
    """处理戳一戳事件 (简化版：仅记录日志)。"""
    _naplog(f"👉 收到戳一戳事件: {json.dumps(data, ensure_ascii=False)[:100]}")


# ==========================================
# 6. 反向 WS 服务端处理 (供 server.py 挂载)
# ==========================================

async def handle_napcat_ws(scope, receive, send):
    """
    反向 WebSocket 处理函数。
    本地 NapCat 作为客户端连接到本网关的 /qq-ws 路径。
    """
    global _napcat_connected, _napcat_ws_send, _napcat_last_connected_at, _napcat_status_message

    # 握手
    await send({"type": "websocket.accept"})
    _napcat_connected = True
    _napcat_ws_send = send
    _napcat_last_connected_at = time.time()
    _napcat_status_message = "已连接"
    _naplog("✅ NapCat 反向 WS 已连接")

    try:
        while True:
            try:
                msg = await receive()
            except Exception:
                break
            if msg["type"] == "websocket.disconnect":
                break
            if msg["type"] != "websocket.receive":
                continue
            raw_text = msg.get("text", "")
            if not raw_text:
                continue
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            # 匹配 API 响应
            echo_val = data.get("echo", "")
            if echo_val and echo_val in _napcat_ws_pending:
                future = _napcat_ws_pending[echo_val]
                if not future.done():
                    future.set_result(data)
                continue

            # 心跳
            if data.get("post_type") == "meta_event" and data.get("meta_event_type") == "heartbeat":
                _napcat_last_connected_at = time.time()
                continue

            # 登录事件
            if data.get("post_type") == "meta_event" and data.get("meta_event_type") == "login":
                sub_type = data.get("sub_type", "")
                if "offline" in str(data).lower() or "kick" in str(data).lower():
                    _napcat_status_message = "🔴 QQ 已掉线"
                    _naplog("🚨 QQ 登录失效，需要重新扫码")
                elif sub_type == "login_success":
                    _napcat_status_message = "🟢 QQ 已登录"
                    _naplog("✅ QQ 已重新登录")
                continue

            # 通知事件
            if data.get("post_type") == "notice":
                if "offline" in str(data).lower():
                    _napcat_status_message = "🔴 QQ 已掉线"
                elif data.get("notice_type") == "notify" and data.get("sub_type") == "poke":
                    try:
                        await _handle_poke_event(send, data, NAPCAT_ALLOWED_GROUPS_LIST)
                    except Exception:
                        pass
                continue

            # 消息事件
            if data.get("post_type") != "message":
                continue
            try:
                await _process_napcat_message(data, send)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _napcat_ws_send = None
        _napcat_connected = False
        _napcat_status_message = "反向 WS 已断开"
        for eid, fut in _napcat_ws_pending.items():
            if not fut.done():
                fut.set_result(None)
        _napcat_ws_pending.clear()
        _naplog("❌ NapCat 反向 WS 连接已关闭")


# ==========================================
# 7. 主动客户端模式 (可选)
# ==========================================

async def napcat_client_loop():
    """
    主动连接 NapCat 的正向 WS (客户端模式)。
    当无法使用反向 WS 时，可启动此循环。
    """
    if not websockets:
        _naplog("缺少 websockets 库，客户端模式无法启动")
        return

    global _napcat_connected, _napcat_last_connected_at, _napcat_status_message

    if not NAPCAT_WS_URL:
        _naplog("未配置 NAPCAT_WS_URL，客户端模式休眠")
        return

    _naplog(f"客户端模式启动，目标: {NAPCAT_WS_URL}")
    delay = RECONNECT_INITIAL_DELAY

    while True:
        try:
            _napcat_status_message = "正在连接..."
            async with websockets.connect(NAPCAT_WS_URL, ping_interval=30, ping_timeout=10, close_timeout=5) as ws:
                _naplog("已连接")
                _napcat_connected = True
                _napcat_last_connected_at = time.time()
                _napcat_status_message = "已连接"
                delay = RECONNECT_INITIAL_DELAY

                async for raw_text in ws:
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        continue
                    if data.get("post_type") == "meta_event":
                        _napcat_last_connected_at = time.time()
                        continue
                    if data.get("post_type") == "notice":
                        continue
                    if data.get("post_type") != "message":
                        continue
                    try:
                        await _process_napcat_message(data, ws.send)
                    except Exception:
                        pass

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            _naplog(f"连接断开: {e}")
            _napcat_connected = False
            _napcat_status_message = f"连接断开: {str(e)[:50]}"
            await _send_disconnect_notification()
        except Exception as e:
            _naplog(f"意外错误: {e}")
            _napcat_connected = False
            _napcat_status_message = f"错误: {str(e)[:50]}"
            await _send_disconnect_notification()

        _naplog(f"{delay}秒后重连...")
        await asyncio.sleep(delay)
        delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)


async def _check_napcat_login_status():
    """通过 HTTP 接口检查登录状态并获取二维码 (如可用)。"""
    if not _requests or not NAPCAT_HTTP_URL:
        return None
    try:
        url = f"{NAPCAT_HTTP_URL}/get_login_info"
        resp = _requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                login_info = data.get("data", {})
                if login_info.get("user_id"):
                    _set_napcat_qr_code(None)
                    return {"status": "logged_in", "user_id": login_info["user_id"], "nickname": login_info.get("nickname", "")}
    except Exception as e:
        _naplog(f"⚠️ 检查登录状态失败: {e}")

    try:
        url = f"{NAPCAT_HTTP_URL}/get_qr_code"
        resp = _requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                qr_url = data.get("data", {}).get("url") or data.get("data", {}).get("qr_code")
                if qr_url:
                    _set_napcat_qr_code(qr_url)
                    return {"status": "need_login", "qr_code": qr_url}
    except Exception as e:
        _naplog(f"⚠️ 获取二维码失败: {e}")

    return None
