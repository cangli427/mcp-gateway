"""
通用 MCP 网关服务端 (Generic MCP Gateway Server) - 瘦身版
=========================================================
这是一个基于 FastMCP 的通用网关架构模板，提供：
- 多工具注册 (@mcp.tool)
- 多 LLM 客户端抽象
- 数据库持久化 (Supabase)
- 记忆 / 画像 系统
- 邮件发送 (Resend)
- QQ 消息推送 (NapCat)

部署：直接运行 python server.py，或通过 uvicorn 部署。
配置：所有敏感信息通过环境变量注入。
"""

import os
import re
import json

# 自动加载同目录下的 .env 文件（本地开发用；云端部署由平台注入环境变量）
# 必须在读取任何 os.environ.get(...) 之前执行，否则 .env 里的密钥不生效。
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import time
import uuid
import asyncio
import datetime
import requests
from functools import wraps

import uvicorn
from mcp.server.fastmcp import FastMCP

# ==========================================
# 1. 全局配置 & 客户端初始化
# ==========================================

mcp = FastMCP("GenericGateway")

# 保留启动时的原始环境变量快照，支持热更新回滚
ORIGINAL_ENV = dict(os.environ)

# 🛡️ 接口安全密钥：所有 /api/* 接口必须校验（防止未授权调用）
API_SECRET = os.environ.get("API_SECRET", "").strip()

# ---------- 数据库客户端 (Supabase) ----------
supabase = None
try:
    from supabase import create_client
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Supabase 初始化失败: {e}")

# ---------- 长期记忆客户端 (Mem0 + Pinecone 双写) ----------
# 还原原版 HybridMemoryClient：Mem0 为主，Pinecone 兜底双写，保证记忆不丢
MEM0_API_KEY = os.environ.get("MEM0_API_KEY", "").strip()
MEM0_USER_ID = os.environ.get("MEM0_USER_ID", "default").strip()
PINECONE_KEY = os.environ.get("PINECONE_API_KEY", "").strip()

try:
    from mem0 import MemoryClient
except ImportError:
    MemoryClient = None

try:
    from pinecone import Pinecone
except ImportError:
    Pinecone = None


class HybridMemoryClient:
    """记忆双写客户端：Mem0 主路 + Pinecone 兜底，任一故障不影响记忆持久化。"""

    def __init__(self):
        self.mem0 = MemoryClient(api_key=MEM0_API_KEY) if MEM0_API_KEY and MemoryClient else None
        self.pc = Pinecone(api_key=PINECONE_KEY) if PINECONE_KEY and Pinecone else None
        self.index_name = os.environ.get("PINECONE_INDEX_NAME", "notion-brain-v2")
        self.index = self.pc.Index(self.index_name) if self.pc else None

    def search(self, query, user_id=None, filters=None, limit=3):
        user_id = user_id or MEM0_USER_ID
        # 1. 优先 Mem0，但必须确认它确实返回了结果
        if self.mem0:
            try:
                safe_filters = filters if filters else {"user_id": user_id}
                res = self.mem0.search(query=query, filters=safe_filters, limit=limit)
                res_list = res.get("results", res) if isinstance(res, dict) else res
                if isinstance(res_list, list) and len(res_list) > 0:
                    return res
            except Exception as e:
                print(f"⚠️ Mem0 搜索异常: {e}")
        # 2. Mem0 无果则强制查询 Pinecone
        if self.index:
            try:
                vec = _get_embedding(query)
                if vec:
                    r = self.index.query(vector=vec, top_k=limit, include_metadata=True)
                    return {"results": [{"memory": m.metadata.get("text", ""), "id": m.id}
                                        for m in r.matches if m.metadata]}
            except Exception as e:
                print(f"❌ Pinecone 搜索失败: {e}")
        return []

    def add(self, messages, user_id=None):
        user_id = user_id or MEM0_USER_ID
        success = False
        if self.mem0:
            try:
                self.mem0.add(messages, user_id=user_id)
                success = True
            except Exception as e:
                print(f"⚠️ Mem0 写入异常: {e}")
        # 同步双写 Pinecone（移除 early return，保证兜底）
        if self.index:
            try:
                text = " | ".join([f"{m.get('role')}: {m.get('content')}" for m in messages if isinstance(m, dict)]) if isinstance(messages, list) else str(messages)
                vec = _get_embedding(text)
                if vec:
                    self.index.upsert(vectors=[{"id": str(uuid.uuid4()), "values": vec,
                                                "metadata": {"text": text, "user_id": user_id}}])
                    success = True
            except Exception as e:
                print(f"❌ Pinecone 写入失败: {e}")
        return success

    def get_all(self, user_id=None):
        user_id = user_id or MEM0_USER_ID
        if self.mem0:
            try:
                return self.mem0.get_all(user_id=user_id)
            except Exception:
                pass
        return []

    def delete(self, memory_id):
        if self.mem0:
            try:
                self.mem0.delete(memory_id)
            except Exception:
                pass
        if self.index:
            try:
                self.index.delete(ids=[memory_id])
            except Exception:
                pass
        return True


mem0_client = HybridMemoryClient()

# ---------- HTTP 会话 (连接池加速) ----------
http_session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=3)
http_session.mount('http://', adapter)
http_session.mount('https://', adapter)

# ---------- 管理员邮箱 (从环境变量读取，兼容原版变量名) ----------
MY_EMAIL = os.environ.get("MY_EMAIL", "").strip() or os.environ.get("ADMIN_EMAIL", "").strip()
RESEND_KEY = os.environ.get("RESEND_API_KEY", "").strip()


# ==========================================
# 记忆分类宪法 (Memory Taxonomy)
# ==========================================
class MemoryType:
    STREAM = "流水"       # 权重 1: 碎碎念、GPS（短期，可清理）
    EPISODIC = "记事"     # 权重 4: 日记、发生了某事
    IDEA = "灵感"         # 权重 7: 脑洞、笔记
    EMOTION = "情感"      # 权重 9: 核心回忆、高光时刻
    FACT = "画像"         # 权重 10: 静态事实


WEIGHT_MAP = {
    MemoryType.STREAM: 1, MemoryType.EPISODIC: 4, MemoryType.IDEA: 7,
    MemoryType.EMOTION: 9, MemoryType.FACT: 10,
}


# ==========================================
# 2. 核心辅助函数
# ==========================================

def mcp_error_handler(func):
    """统一的工具异常捕获装饰器，避免单次工具报错导致整个网关崩溃。"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return f"❌ 工具执行出错: {e}"
    return wrapper


def _get_llm_client(provider: str = "openai"):
    """
    多模型客户端工厂：按角色返回对应的 LLM 客户端。
    完整还原原版 5 种 provider，所有密钥/地址/模型名均从环境变量读取。
    - openai    : 通用默认模型 (OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME)
    - main_chat : 主对话模型，可从数据库 llm_settings 动态覆盖 (CHAT_API_KEY / CHAT_BASE_URL / CHAT_MODEL_NAME)
    - silicon1  : 硅基流动便宜模型 (SILICON1_API_KEY / SILICON1_BASE_URL / SILICON1_MODEL_NAME)
    - vision    : 视觉/OCR 模型 (VISION_API_KEY / VISION_BASE_URL / VISION_MODEL_NAME)
    - voice     : 语音/STT 模型，回退到 OPENAI (VOICE_API_KEY / VOICE_BASE_URL)
    """
    from openai import OpenAI
    client = None
    model_name = "gpt-3.5-turbo"

    if provider == "silicon1":
        api_key = os.environ.get("SILICON1_API_KEY", "").strip()
        base_url = os.environ.get("SILICON1_BASE_URL", "https://api.siliconflow.cn/v1")
        client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
        model_name = os.environ.get("SILICON1_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
    elif provider == "main_chat":
        # 优先从数据库读取动态配置，回退到环境变量
        db_conf = {}
        if supabase:
            try:
                res = supabase.table("user_facts").select("value").eq("key", "llm_settings").execute()
                db_conf = json.loads(res.data[0]['value']) if res.data else {}
            except Exception:
                db_conf = {}
        api_key = db_conf.get("key") or os.environ.get("CHAT_API_KEY", "").strip()
        base_url = db_conf.get("url") or os.environ.get("CHAT_BASE_URL", "https://api.minimaxi.com/v1")
        model_name = db_conf.get("model") or os.environ.get("CHAT_MODEL_NAME", "abab6.5s-chat")
        client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
    elif provider == "vision":
        api_key = os.environ.get("VISION_API_KEY", "").strip()
        base_url = os.environ.get("VISION_BASE_URL", "").strip()
        client = OpenAI(api_key=api_key, base_url=base_url if base_url else None) if api_key else None
        model_name = os.environ.get("VISION_MODEL_NAME", "gpt-4o-mini")
    elif provider == "voice":
        api_key = os.environ.get("VOICE_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()
        base_url = os.environ.get("VOICE_BASE_URL", "https://api.openai.com/v1")
        client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
    else:
        # 默认 openai provider
        api_key = os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("DEFAULT_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("DEFAULT_BASE_URL", "")).strip()
        client = OpenAI(api_key=api_key, base_url=base_url if base_url else None) if api_key else None
        model_name = os.environ.get("OPENAI_MODEL_NAME", os.environ.get("DEFAULT_MODEL_NAME", "gpt-3.5-turbo"))

    if client:
        client.custom_model_name = model_name
    return client


async def _ask_llm_async(client, prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    """异步调用 LLM，自动剥离 <think> 标签，返回干净的纯文本。"""
    if not client:
        return ""
    model_name = getattr(client, 'custom_model_name', os.environ.get("OPENAI_MODEL_NAME", "gpt-3.5-turbo"))
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    def _call():
        return client.chat.completions.create(model=model_name, messages=messages, temperature=temperature)

    try:
        resp = await asyncio.to_thread(_call)
        if not resp.choices:
            return ""
        raw_text = resp.choices[0].message.content.strip()
        # 剥离深度思考模型的 <think>...</think> 内部推理块
        return re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        return ""


def _get_now_bj() -> datetime.datetime:
    """获取北京时间 (UTC+8)。如需修改时区，改此处即可。"""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def _save_memory_to_db(title: str, content: str, category: str = "流水", mood: str = "平静", tags: str = ""):
    """将一条记忆/事件写入 Supabase memories 表，自动计算重要度权重并推断标签。"""
    if not supabase:
        return
    try:
        if category not in WEIGHT_MAP:
            mapping = {"日记": MemoryType.EPISODIC, "Note": MemoryType.IDEA,
                       "GPS": MemoryType.STREAM, "重要": MemoryType.EMOTION}
            category = mapping.get(category, MemoryType.STREAM)
        importance = WEIGHT_MAP.get(category, 1)

        if not tags:
            content_lower = content.lower()
            if any(w in content_lower for w in ["爱", "喜欢", "讨厌", "恨"]):
                tags = "情感,偏好"
            elif any(w in content_lower for w in ["吃", "喝", "买"]):
                tags = "消费,生活"
            elif any(w in content_lower for w in ["代码", "bug", "写"]):
                tags = "工作,Dev"
            else:
                tags = "System"

        data = {
            "title": title,
            "content": content,
            "category": category,
            "mood": mood,
            "tags": tags,
            "importance": importance,
            "created_at": _get_now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        }
        supabase.table("memories").insert(data).execute()
    except Exception as e:
        print(f"⚠️ 写入记忆失败: {e}")


def _get_embedding(text: str):
    """调用向量嵌入 API 生成文本向量 (供 Pinecone 记忆检索用)。变量名兼容 DOUBAO_API_KEY。"""
    try:
        api_key = os.environ.get("DOUBAO_API_KEY", "").strip()
        embed_endpoint = os.environ.get("DOUBAO_EMBEDDING_EP", "").strip()
        if not api_key or not embed_endpoint:
            return []
        url = "https://api.siliconflow.cn/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": embed_endpoint, "input": text}
        response = http_session.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            raw_vec = data["data"][0].get("embedding", [])
            if raw_vec:
                return [float(x) for x in raw_vec]
        return []
    except Exception:
        return []


def _push_wechat(text: str, title: str = "通知"):
    """
    通用消息推送函数。
    默认通过 Telegram Bot 推送，可扩展为其他渠道。
    所有凭证从环境变量读取。
    """
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(f"⚠️ 未配置 Telegram，跳过推送: {title}")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": f"*{title}*\n\n{text}",
            "parse_mode": "Markdown"
        }, timeout=15)
    except Exception as e:
        print(f"⚠️ 推送失败: {e}")


def _send_email_helper(subject: str, content: str, is_html: bool = False):
    """通过 Resend 发送邮件 (兼容原版 RESEND_API_KEY / MY_EMAIL 变量名)。"""
    if not RESEND_KEY or not MY_EMAIL:
        return "❌ 邮件配置缺失 (RESEND_API_KEY / MY_EMAIL)"
    try:
        payload = {
            "from": "onboarding@resend.dev",
            "to": [MY_EMAIL],
            "subject": subject,
            "html" if is_html else "text": content,
        }
        requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {RESEND_KEY}"}, json=payload, timeout=20)
        return "✅ 邮件已发送"
    except Exception as e:
        return f"❌ 发送失败: {e}"


# ============================================================
# 🗑️ [已移除] _clean_email_body - 邮件正文清洗（仅被已移除的Gmail功能使用）
# ============================================================
# def _clean_email_body(text: str) -> str:
#     """清洗邮件正文中的 HTML 标签和多余空白。"""
#     text = re.sub(r'<[^>]+>', '', text)
#     text = re.sub(r'\n{3,}', '\n\n', text)
#     return text.strip()


def _get_current_persona() -> str:
    """读取当前 AI 人设：优先数据库 user_facts 动态人设，回退环境变量 AI_PERSONA。"""
    base_persona = os.environ.get("AI_PERSONA", "你是一个通用智能助手。").strip()
    if supabase:
        try:
            res = supabase.table("user_facts").select("value").eq("key", "sys_ai_persona").execute()
            if res.data:
                base_persona = res.data[0]['value']
        except Exception:
            pass
    weave_instruction = "（如果对话中自然联想到相关回忆，可以简短提及，但保持对话自然流畅。）"
    return f"{base_persona}\n\n{weave_instruction}"


def _format_time_cn(iso_str: str) -> str:
    """UTC ISO 字符串 → 北京时间 (MM-DD HH:MM)。"""
    if not iso_str:
        return "未知时间"
    try:
        dt = datetime.datetime.fromisoformat(str(iso_str).replace('Z', '+00:00'))
        return (dt + datetime.timedelta(hours=8)).strftime('%m-%d %H:%M')
    except Exception:
        return "未知时间"


def _get_latest_gps_record():
    """读取 Supabase device_data 表最新一条定位记录。"""
    if not supabase:
        return None
    try:
        res = supabase.table("device_data").select("*").order("timestamp", desc=True).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def _gps_to_address(lat, lon):
    """经纬度 → 中文地址 (OpenStreetMap 反向地理编码)。"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1&accept-language=zh-CN"
        resp = http_session.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("display_name", f"坐标点 ({lat},{lon})")
    except Exception:
        pass
    return f"坐标点: {lat}, {lon}"


async def get_latest_diary(limit: int = 15) -> str:
    """
    【核心大脑】极速混合记忆流 (Token 优化版)
    加载最新长期总结 + 近期短期记忆 + 记忆小屋动态 + 失联时长感知。
    """
    if not supabase:
        return "（数据库未连接）"
    try:
        # 并发拉取：长期总结 / 近期记忆 / 记忆小屋动态
        def _fetch_recent():
            return supabase.table("memories").select("*").order("created_at", desc=True).limit(limit).execute()
        def _fetch_house():
            return supabase.table("memory_house").select("*").order("created_at", desc=True).limit(15).execute()
        res_recent, res_house = await asyncio.gather(
            asyncio.to_thread(_fetch_recent),
            asyncio.to_thread(_fetch_house),
        )

        # 记忆小屋动态流
        house_stream = ""
        if res_house and res_house.data:
            house_stream = "\n🏡 【近期小屋生活动态】:\n"
            for h in sorted(res_house.data, key=lambda x: x.get('created_at', '')):
                time_str = _format_time_cn(h.get('created_at'))
                locked = "🔒" if h.get('is_locked') else ""
                house_stream += f"{time_str} {locked}在【{h.get('room', '未知')}】{h.get('action_type', '活动')}: {str(h.get('content', ''))[:80]}...\n"

        # 主记忆流
        memory_stream = "🧠 【当前大脑状态】:\n"
        if not res_recent or not res_recent.data:
            memory_stream += "📭 (一片空白)\n"
        else:
            for data in res_recent.data:
                time_str = _format_time_cn(data.get('created_at'))
                cat = data.get('category', '未知')
                title = data.get('title', '无题')
                mood_str = f" | Mood:{data.get('mood')}" if data.get('mood') else ""
                memory_stream += f"{time_str} [{cat}] 【{title}】: {data.get('content', '')}{mood_str}\n"
            memory_stream += house_stream

        return memory_stream
    except Exception as e:
        return f"（记忆读取失败: {e}）"


async def where_is_user() -> str:
    """【查岗专用】从 Supabase 读取实时位置 + 天气 + 今日 App 轨迹。"""
    if not supabase:
        return "❌ 数据库未连接"
    try:
        data = await asyncio.to_thread(_get_latest_gps_record)
        if not data:
            return "📍 暂无位置记录。"

        time_str = _format_time_cn(data.get("timestamp"))
        weather_info = ""
        lat, lon = data.get("location_latitude") or data.get("lat"), data.get("location_longitude") or data.get("lon")

        if lat and lon:
            def _get_weather():
                try:
                    amap_key = os.environ.get("AMAP_API_KEY", "").strip()
                    if amap_key:
                        regeo_url = f"https://restapi.amap.com/v3/geocode/regeo?location={lon},{lat}&key={amap_key}"
                        regeo_res = requests.get(regeo_url, timeout=4).json()
                        if regeo_res.get("status") == "1":
                            adcode = regeo_res.get("regeocode", {}).get("addressComponent", {}).get("adcode")
                            if adcode:
                                weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={amap_key}"
                                weather_res = requests.get(weather_url, timeout=4).json()
                                if weather_res.get("status") == "1" and weather_res.get("lives"):
                                    live = weather_res["lives"][0]
                                    return f" ☁️ {live.get('weather')} {live.get('temperature')}℃"
                except Exception:
                    pass
                return ""
            weather_info = await asyncio.to_thread(_get_weather)

        current_status = f"🛰️ 实时状态：\n📍 {data.get('location_address', '未知')}{weather_info}\n📱 当前活跃应用: {data.get('foreground_app', '未知')}\n(更新于: {time_str})"

        # 今日 App 轨迹
        def _get_apps():
            time_threshold = (datetime.datetime.utcnow() - datetime.timedelta(hours=12)).isoformat()
            res = supabase.table("device_data").select("timestamp, foreground_app").gt("timestamp", time_threshold).order("timestamp").execute()
            if not res.data:
                return "暂无轨迹"
            timeline, last_app = [], ""
            for r in res.data:
                app_name = (r.get("foreground_app") or "").strip()
                if not app_name:
                    continue
                ts = _format_time_cn(r.get("timestamp"))[-5:]
                if app_name != last_app:
                    timeline.append(f"[{ts}] {app_name}")
                    last_app = app_name
            if not timeline:
                return "无切换记录"
            if len(timeline) > 15:
                timeline = ["..."] + timeline[-15:]
            return " ➡️ ".join(timeline)
        app_timeline = await asyncio.to_thread(_get_apps)
        return f"{current_status}\n\n📱 今日手机轨迹: {app_timeline}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


# ==========================================
# 3. MCP 工具定义 (通用示例)
# ==========================================

@mcp.tool()
async def echo(text: str):
    """【回声测试】用于验证网关是否正常工作。"""
    return f"🔔 网关正常运行中，收到: {text}"


@mcp.tool()
@mcp_error_handler
async def save_memory(title: str, content: str, category: str = "事件"):
    """【保存记忆】将一条信息持久化到数据库，同时双写到 Mem0/Pinecone 向量库。"""
    await asyncio.to_thread(_save_memory_to_db, title, content, category)
    try:
        await asyncio.to_thread(mem0_client.add, [{"role": "assistant", "content": f"{title}: {content}"}])
    except Exception:
        pass
    return f"✅ 记忆已保存: {title}"


@mcp.tool()
@mcp_error_handler
async def search_memory(query: str):
    """【搜索记忆】先查向量库 (语义相似)，再查数据库 (关键词模糊)，合并结果。"""
    ans_parts = []
    # 1. 向量语义搜索
    try:
        vec_results = await asyncio.to_thread(mem0_client.search, query)
        if vec_results:
            res_list = vec_results.get("results", vec_results) if isinstance(vec_results, dict) else vec_results
            if isinstance(res_list, list) and res_list:
                ans_parts.append("🧠 【语义相似记忆】:")
                for r in res_list[:3]:
                    mem = r.get("memory", r.get("text", str(r))) if isinstance(r, dict) else str(r)
                    ans_parts.append(f"- {mem}")
    except Exception:
        pass
    # 2. 数据库关键词搜索
    if supabase:
        def _query():
            return supabase.table("memories").select("id, title, content, importance").or_(
                f"title.ilike.%{query}%,content.ilike.%{query}%"
            ).order("importance", desc=True).limit(5).execute()
        sb_res = await asyncio.to_thread(_query)
        if sb_res and sb_res.data:
            ans_parts.append("🔍 【关键词匹配记忆】:")
            for r in sb_res.data:
                ans_parts.append(f"- 【{r.get('title', '无题')}】: {r['content']}")
    if not ans_parts:
        return "🧠 暂未搜到相关记忆。"
    return "\n".join(ans_parts)


@mcp.tool()
@mcp_error_handler
async def manage_user_fact(key: str, value: str):
    """【管理用户画像】新增或更新一条用户事实 (key-value)。"""
    if not supabase:
        return "❌ 数据库未连接"
    def _upsert():
        return supabase.table("user_facts").upsert(
            {"key": key, "value": value, "confidence": 1.0}, on_conflict="key"
        ).execute()
    await asyncio.to_thread(_upsert)
    return f"✅ 画像已更新: {key} -> {value}"


@mcp.tool()
@mcp_error_handler
async def get_user_profile():
    """【获取用户画像】读取所有用户事实。"""
    if not supabase:
        return "❌ 数据库未连接"
    def _fetch():
        return supabase.table("user_facts").select("key, value").execute()
    response = await asyncio.to_thread(_fetch)
    if not response.data:
        return "👤 用户画像为空"
    return "📋 【用户画像】:\n" + "\n".join([f"- {i['key']}: {i['value']}" for i in response.data])


@mcp.tool()
@mcp_error_handler
async def organize_knowledge_base(target: str, action: str, query_or_data: str = ""):
    """
    【知识库管理】通用 CRUD 工具。
    target: "profile" (用户画像) | "memory" (记忆库)
    action: "list" | "search" | "read" | "update" | "delete"
    """
    if not supabase:
        return "❌ 数据库未连接"
    try:
        if target == "profile":
            if action == "list":
                res = await asyncio.to_thread(lambda: supabase.table("user_facts").select("*").execute())
                return json.dumps(res.data, ensure_ascii=False, indent=2)
            elif action == "update":
                data = json.loads(query_or_data)
                await asyncio.to_thread(lambda: supabase.table("user_facts").upsert(data).execute())
                return f"✅ 已更新: {data}"
            elif action == "delete":
                await asyncio.to_thread(lambda: supabase.table("user_facts").delete().eq("key", query_or_data).execute())
                return f"✅ 已删除: {query_or_data}"

        elif target == "memory":
            if action == "list":
                res = await asyncio.to_thread(lambda: supabase.table("memories").select("id, created_at, category, title, content").order("created_at", desc=True).limit(20).execute())
                return json.dumps(res.data, ensure_ascii=False, indent=2)
            elif action == "search":
                res = await asyncio.to_thread(lambda: supabase.table("memories").select("id, title, content").or_(f"title.ilike.%{query_or_data}%,content.ilike.%{query_or_data}%").limit(15).execute())
                return json.dumps(res.data, ensure_ascii=False, indent=2)
            elif action == "read":
                res = await asyncio.to_thread(lambda: supabase.table("memories").select("*").eq("id", query_or_data).execute())
                return json.dumps(res.data, ensure_ascii=False, indent=2) if res.data else "❌ 未找到"
            elif action == "update":
                data = json.loads(query_or_data)
                mid = data.pop("id", None)
                if not mid:
                    return "❌ 缺少 id"
                await asyncio.to_thread(lambda: supabase.table("memories").update(data).eq("id", mid).execute())
                return f"✅ 记忆 {mid} 已更新"
            elif action == "delete":
                await asyncio.to_thread(lambda: supabase.table("memories").delete().eq("id", query_or_data).execute())
                return f"✅ 记忆 {query_or_data} 已删除"
        return "❌ 未知指令"
    except Exception as e:
        return f"❌ 操作失败: {e}"


@mcp.tool()
async def send_notification(content: str):
    """【发送通知】通过 QQ (NapCat) 推送消息。"""
    try:
        from napcat import send_qq_message, NAPCAT_TARGET_USER
        if NAPCAT_TARGET_USER:
            result = await send_qq_message(int(NAPCAT_TARGET_USER), f"📢 {content}", is_group=False, force_http=True)
            if result:
                return f"✅ 通知已通过 QQ 发送: {content[:100]}"
            return "❌ QQ 发送失败，请检查 NapCat 连接"
        return "❌ 未配置 NAPCAT_TARGET_USER，无法发送通知"
    except Exception as e:
        return f"❌ 通知发送失败: {e}"


# ============================================================
# 🗑️ [已移除] manage_reminder - 提醒/闹钟功能
# ============================================================
# @mcp.tool()
# @mcp_error_handler
# async def manage_reminder(action: str, time_str: str = "", content: str = "", is_repeat: bool = False, reminder_id: str = ""):
#     ... (提醒管理已移除，降低内存占用)
#     return "❌ 提醒功能已移除。"


@mcp.tool()
async def send_email_via_api(subject: str, content: str):
    """【发送邮件】通过配置的邮件服务发送通知邮件给管理员。"""
    return await asyncio.to_thread(_send_email_helper, subject, content)


# ============================================================
# 🗑️ [已移除] web_search - Tavily + DuckDuckGo 搜索
# ============================================================
# @mcp.tool()
# async def web_search(query: str, max_results: int = 5):
#     ... (网页搜索已移除，降低内存占用和依赖)
#     return "❌ 网页搜索功能已移除。"


# ============================================================
# 🗑️ [已移除] 邮件收信 (Gmail API: check_inbox / read_full_email / reply_external_email)
# ============================================================
# def _get_gmail_service(): ... (Gmail OAuth 服务已移除)
# def _parse_gmail_body(payload): ... (邮件解析已移除)
# @mcp.tool() async def check_inbox(...): ... (查收邮件已移除)
# @mcp.tool() async def read_full_email(...): ... (阅读邮件全文已移除)
# @mcp.tool() async def reply_external_email(...): ... (回复邮件已移除)


# ============================================================
# 🗑️ [已移除] Google 日历 (add_calendar_event / get_calendar_events / modify_calendar_event)
# ============================================================
# TARGET_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
# def _get_calendar_service(): ... (Google Calendar API 已移除)
# @mcp.tool() async def add_calendar_event(...): ... (添加日历已移除)
# @mcp.tool() async def get_calendar_events(...): ... (查询日历已移除)
# @mcp.tool() async def modify_calendar_event(...): ... (修改日历已移除)


# ==========================================
# GPS / 记忆小屋 / 生活工具
# ==========================================

@mcp.tool()
@mcp_error_handler
async def manage_memory_house(action: str, room: str = "", activity: str = "", content: str = "", record_id: str = ""):
    """
    【记忆小屋管理】AI 虚拟生活系统，让 AI 在"自己的小屋"里自主活动，产生陪伴感。
    action: "list" (查看动态) | "do" (在房间做某事) | "delete" (删除一条动态)
    room: 卧室/厨房/客厅/书房/阳台 等
    activity: 看书/做饭/听音乐/发呆 等
    """
    if not supabase:
        return "❌ 数据库未连接"
    if action == "list":
        res = await asyncio.to_thread(lambda: supabase.table("memory_house").select("*").order("created_at", desc=True).limit(20).execute())
        if not res.data:
            return "🏡 小屋还空荡荡的，AI 还没开始活动。"
        ans = "🏡 【AI 小屋动态】:\n"
        for h in res.data:
            ts = _format_time_cn(h.get('created_at'))
            locked = "🔒" if h.get('is_locked') else ""
            ans += f"- {ts} {locked}在【{h.get('room','未知')}】{h.get('action_type','活动')}: {str(h.get('content',''))[:60]}\n"
        return ans
    if action == "do":
        if not room or not activity:
            return "❌ 需要 room 和 activity 参数。"
        data = {
            "room": room,
            "action_type": activity,
            "content": content or "",
            "is_locked": False,
            "created_at": _get_now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        }
        await asyncio.to_thread(lambda: supabase.table("memory_house").insert(data).execute())
        return f"✅ AI 在【{room}】开始{activity}了。"
    if action == "delete" and record_id:
        await asyncio.to_thread(lambda: supabase.table("memory_house").delete().eq("id", record_id).execute())
        return f"✅ 小屋动态 {record_id} 已删除。"
    return "❌ 未知操作。"


@mcp.tool()
@mcp_error_handler
async def save_expense(item: str, amount: float, type: str = "餐饮"):
    """【记账】记录一笔花销。type 建议：餐饮/购物/交通/娱乐/日常/其他。"""
    if not supabase:
        return "❌ 数据库未连接"
    def _insert():
        return supabase.table("expenses").insert({
            "item": item, "amount": amount, "type": type,
            "date": datetime.date.today().isoformat()
        }).execute()
    await asyncio.to_thread(_insert)
    return f"✅ 记账成功！\n💰 {item}: {amount}元 ({type})"


@mcp.tool()
@mcp_error_handler
async def check_expense_report(month: str = ""):
    """【查询账单】读取某月消费记录汇总。month 格式 YYYY-MM，默认当月。"""
    if not supabase:
        return "❌ 数据库未连接"
    target_month = month if month else datetime.date.today().strftime("%Y-%m")
    try:
        def _query():
            year, m = map(int, target_month.split("-"))
            start_date = f"{year:04d}-{m:02d}-01"
            end_date = f"{year+1:04d}-01-01" if m == 12 else f"{year:04d}-{m+1:02d}-01"
            return supabase.table("expenses").select("*").gte("date", start_date).lt("date", end_date).execute()
        res = await asyncio.to_thread(_query)
        if not res or not res.data:
            return f"📊 【{target_month} 财务报告】\n本月暂无记账记录。"
        total = 0.0
        type_summary = {}
        details = ""
        for row in res.data:
            amt = float(row.get("amount", 0))
            item = row.get("item", "未知")
            t = row.get("type", "其他")
            date_str = str(row.get("date", ""))[5:10]
            total += amt
            type_summary[t] = type_summary.get(t, 0) + amt
            details += f"- {date_str} | {item}: {amt}元 ({t})\n"
        report = f"📊 【{target_month} 账单汇总】\n💰 总计: {total:.2f} 元\n\n📂 分类:\n"
        for t, amt in sorted(type_summary.items(), key=lambda x: -x[1]):
            report += f"  {t}: {amt:.2f} 元\n"
        report += f"\n📋 明细:\n{details}"
        return report
    except Exception as e:
        return f"❌ 账单查询失败: {e}"


@mcp.tool()
@mcp_error_handler
async def manage_piggy_bank(action: str, amount: float = 0.0, reason: str = ""):
    """
    【零钱罐 / 储蓄罐】管理一个虚拟储值账户。
    action: "check" (查余额) | "add" (存入) | "spend" (支出)
    """
    if not supabase:
        return "❌ 数据库未连接"
    res = await asyncio.to_thread(lambda: supabase.table("user_facts").select("value").eq("key", "piggy_bank").execute())
    current = float(res.data[0]['value']) if res.data else 0.0
    if action == "check":
        return f"🐷 当前余额：{current:.2f} 元。"
    if action == "add":
        current += amount
    elif action == "spend":
        current = max(0.0, current - amount)
    else:
        return "❌ action 只能是 add / spend / check"
    await asyncio.to_thread(lambda: supabase.table("user_facts").upsert({"key": "piggy_bank", "value": str(current), "confidence": 1.0}, on_conflict="key").execute())
    act_str = "存入" if action == "add" else "取出"
    return f"✅ 成功{act_str} {amount} 元！当前余额：{current:.2f} 元。"


# ============================================================
# 🗑️ [已移除] tarot_reading - 塔罗占卜
# ============================================================
# @mcp.tool()
# @mcp_error_handler
# async def tarot_reading(question: str):
#     ... (塔罗占卜已移除)


# ============================================================
# 🗑️ [已移除] 多媒体: render_html_to_image / compose_music / cover_existing_song
# ============================================================
# @mcp.tool() async def render_html_to_image(...): ... (HTML转图片已移除)
# @mcp.tool() async def compose_music(...): ... (AI作曲已移除)
# @mcp.tool() async def cover_existing_song(...): ... (AI翻唱已移除)


# ============================================================
# 🗑️ [已移除] 坚果云/WebDAV 笔记 (Obsidian)
# (_scan_all_md_files / list_obsidian_cloud / read_obsidian_cloud / write_obsidian_cloud 已移除)
# ============================================================


# ============================================================
# 🗑️ [已移除] AI 音乐 (Replicate RVC)
# (compose_music / cover_existing_song 已移除)
# ============================================================


# ==========================================
# 4. 启动入口
# ==========================================

from gateway import HostFixMiddleware
from heartbeat import start_autonomous_life


def _print_config_report():
    """启动时扫描环境变量，打印功能可用性清单（配置体检报告）。"""
    def _ok(key):
        return bool(os.environ.get(key, "").strip())

    items = [
        ("LLM (默认模型)",    _ok("OPENAI_API_KEY") or _ok("DEFAULT_API_KEY"), os.environ.get("OPENAI_MODEL_NAME", os.environ.get("DEFAULT_MODEL_NAME", "未设置"))),
        ("主对话 (CHAT)",     _ok("CHAT_API_KEY"),     os.environ.get("CHAT_MODEL_NAME", "未设置")),
        ("硅基 (SILICON1)",   _ok("SILICON1_API_KEY"), os.environ.get("SILICON1_MODEL_NAME", "未设置")),
        ("视觉 (VISION)",     _ok("VISION_API_KEY"),   os.environ.get("VISION_MODEL_NAME", "未设置")),
        ("语音 (VOICE)",      _ok("VOICE_API_KEY") or _ok("OPENAI_API_KEY"), "已配置" if _ok("VOICE_API_KEY") or _ok("OPENAI_API_KEY") else "未配置"),
        ("数据库 (Supabase)", _ok("SUPABASE_URL") and _ok("SUPABASE_KEY"), "已连接" if supabase else "未连接"),
        ("长期记忆 (Mem0)",   _ok("MEM0_API_KEY"),     "已启用" if mem0_client.mem0 else "未配置"),
        ("向量库 (Pinecone)", _ok("PINECONE_API_KEY"), "已启用" if mem0_client.index else "未配置"),
        ("向量嵌入 (Doubao)", _ok("DOUBAO_API_KEY"),   "已配置" if _ok("DOUBAO_API_KEY") else "未配置"),
        ("邮件发送 (Resend)", _ok("RESEND_API_KEY") and _ok("MY_EMAIL"), "已配置" if _ok("RESEND_API_KEY") else "未配置"),
        ("QQ 机器人 (NapCat)",_ok("NAPCAT_WS_URL") or _ok("NAPCAT_HTTP_URL"), "已配置" if (_ok("NAPCAT_WS_URL") or _ok("NAPCAT_HTTP_URL")) else "未配置"),
        ("地图/GPS (高德)",    _ok("AMAP_API_KEY"),     "已配置" if _ok("AMAP_API_KEY") else "未配置"),
        ("接口安全密钥",      _ok("API_SECRET"),        "已配置" if _ok("API_SECRET") else "⚠️ 未配置(危险)"),
        # 🗑️ [已移除] Telegram推送 / Gmail日历 / 网页搜索 / AI音乐 / 云端笔记 / HTML转图
    ]
    enabled = sum(1 for _, ok, _ in items if ok)
    total = len(items)
    line = "═" * 44
    print(f"\n╔{line}╗")
    print(f"║{'🔍 配置体检报告':^36}║")
    print(f"╠{line}╣")
    for name, ok, detail in items:
        mark = "✅" if ok else "❌"
        text = f" {mark} {name:<16} → {detail}"
        print(f"║{text:<44}║")
    print(f"╠{line}╣")
    print(f"║{'已启用 ' + str(enabled) + '/' + str(total) + ' 项功能，网关正常运行中':^36}║")
    print(f"╚{line}╝\n")


if __name__ == "__main__":
    _print_config_report()
    # 启动后台心跳协程
    start_autonomous_life()
    port = int(os.environ.get("PORT", 10000))
    app = HostFixMiddleware(mcp.sse_app())
    print(f"🚀 Generic MCP Gateway running on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
