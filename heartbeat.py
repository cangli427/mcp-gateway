"""
通用后台心跳模块 (Generic Background Heartbeat) - 瘦身版
=========================================================
负责启动一系列后台异步协程 (运行在独立 daemon 线程中)：
- 自主生命循环：定时主动思考/问候
- 每日日记生成：深夜自动整理昨日记忆
- 消息总结器：定期汇总未处理消息
- 环境变量同步：从数据库热更新配置

所有协程均通过延迟导入 (函数内 import) 避免 server.py 的循环依赖。
"""

import os
import json
import time
import random
import asyncio
import datetime
import threading

# ==========================================
# 注入 QQ 机器人发送通道（通行证）
# ==========================================
from napcat import send_qq_message, NAPCAT_TARGET_USER

# 全局：下一次主动唤醒的时间戳，可供前端展示
global_next_wake_time = 0.0


# ==========================================
# 1. 自主生命循环 (主动问候)
# ==========================================

async def async_autonomous_life():
    """定时主动思考并发送问候，让 AI 拥有"自主生命感"。"""
    # 延迟导入，避免循环依赖
    from server import (
        _get_llm_client, _ask_llm_async, _push_wechat,
        _save_memory_to_db, _get_now_bj, _get_current_persona,
        get_latest_diary, where_is_user, supabase
    )

    global global_next_wake_time
    print("💓 自主生命循环已上线...")

    # 触发间隔（秒），默认 2 小时，可通过环境变量调整
    interval = int(os.environ.get("HEARTBEAT_INTERVAL", 7200))

    while True:
        # 随机化下一次唤醒时间，避免过于机械
        wake_jitter = random.randint(-600, 600)
        global_next_wake_time = time.time() + interval + wake_jitter

        await asyncio.sleep(interval + wake_jitter)

        try:
            client = _get_llm_client("main_chat")
            if not client:
                continue

            recent_mem = await get_latest_diary()
            curr_loc = await where_is_user()
            curr_persona = _get_current_persona()
            now_bj = _get_now_bj()

            prompt = f"""
            当前时间: {now_bj.strftime('%Y-%m-%d %H:%M')} (星期{now_bj.isoweekday()})
            当前人设: {curr_persona}
            近期互动记录: {recent_mem}
            用户大概状态: {curr_loc}

            请基于以上信息，用符合人设的口吻主动发一条简短问候 (50 字内)。
            要求自然、有温度，不要提"系统/闹钟/定时"，直接像真人突然想起对方那样说话。
            纯文本输出，禁止使用表情代码或 URL。
            """

            ai_msg = await _ask_llm_async(client, prompt, temperature=0.85)
            if ai_msg:
                await asyncio.to_thread(_push_wechat, ai_msg, "💌 主动问候")
                # ========== 同步推送主动问候到 QQ（强制 HTTP，心跳不在 WS 线程内）==========
                if NAPCAT_TARGET_USER:
                    try:
                        result = await send_qq_message(int(NAPCAT_TARGET_USER), ai_msg, is_group=False, force_http=True)
                        if result is None:
                            print(f"❌ [Heartbeat] QQ 发送失败（HTTP 也未成功，检查 NAPCAT_HTTP_URL）")
                        else:
                            print(f"🌟 [Heartbeat] 已成功将自主问候同步推送至 QQ: {NAPCAT_TARGET_USER}")
                    except Exception as e:
                        print(f"❌ [Heartbeat] 推送 QQ 失败: {e}")
                await asyncio.to_thread(
                    _save_memory_to_db, "🤖 主动问候",
                    f"主动发送: {ai_msg}", "流水", "主动", "Heartbeat"
                )
                print(f"💓 [自主生命] 已发送主动问候: {ai_msg[:30]}...")
        except Exception as e:
            print(f"❌ 自主生命循环出错: {e}")


# ==========================================
# 1.5 每日日记生成 (深度睡眠模式)
# ==========================================

async def _perform_deep_dreaming():
    """
    🌙【深夜日记模式】每日自动生成"昨日回溯"日记。
    拉取昨日全部对话流水 → 调用便宜模型生成第一人称日记 → 归档至 memories。
    同时执行周/月/年三级宏观记忆收束（按日期条件触发）。
    全程异常隔离，失败只记日志，不影响主流程。
    """
    from server import (
        _get_llm_client, _ask_llm_async, _save_memory_to_db,
        _send_email_helper, _get_now_bj, supabase, MemoryType
    )

    AI_NAME = os.environ.get("AI_NAME", "AI")
    USER_NAME = os.environ.get("USER_NAME", "用户")

    print("🌌 进入深度睡眠：正在整理昨日记忆，准备生成日记...")
    try:
        now_bj = _get_now_bj()
        yesterday = (now_bj - datetime.timedelta(days=1)).date()
        # 精确范围：[昨天0点, 今天0点)，避免拉到今天的数据
        iso_start = f"{yesterday.isoformat()} 00:00:00"
        iso_end = f"{now_bj.date().isoformat()} 00:00:00"

        # 拉取昨日全部记忆（流水 + 已归档总结）
        def _fetch_yesterday():
            return supabase.table("memories").select(
                "title, created_at, category, content, mood"
            ).gt("created_at", iso_start).lt("created_at", iso_end).order("created_at").execute()

        mem_res = await asyncio.to_thread(_fetch_yesterday)
        if not mem_res.data:
            print("🌌 昨日无记忆数据，跳过日记生成。")
            return

        # 拼接上下文（每条截断 500 字防 token 爆炸，整体上限 8 万字）
        context = f"【昨日剧情 {yesterday}】:\n"
        for m in mem_res.data:
            content_preview = str(m.get('content', ''))[:500]
            ctx_time = str(m.get('created_at', ''))[11:16]
            context += f"[{ctx_time}] 【{m.get('title', '无题')}】 {content_preview} (Mood:{m.get('mood', '?')})\n"
        if len(context) > 80000:
            context = context[-80000:]

        # 获取主对话模型客户端（用户要求：总结类一律用聊天模型，不用便宜/默认模型）
        client = _get_llm_client("main_chat")
        if not client:
            print("⚠️ 未配置 CHAT_API_KEY，日记生成跳过（LLM 客户端缺失）。")
            return

        # 步骤1：生成每日日记（第一人称视角）
        prompt_summary = (
            f"{context}\n\n"
            f"请以【{AI_NAME}】的第一人称视角，将上述碎片整理成一篇具体日记。"
            f"⚠️严重警告：必须严格区分清楚【{AI_NAME}(我)】和【{USER_NAME}(对方)】各自说了什么、做了什么，"
            f"绝对不能张冠李戴搞混主语！直接输出纯文本，勿加前言后语及格式符号。"
        )
        summary = await _ask_llm_async(client, prompt_summary, temperature=0.7)

        if summary:
            await asyncio.to_thread(
                _save_memory_to_db,
                f"📅 昨日回溯: {yesterday}", summary,
                MemoryType.EMOTION, "平静", "Core_Cognition"
            )
            await asyncio.to_thread(_send_email_helper, f"📔 日记总结 ({yesterday})", summary)
            # ========== 同步推送日记总结到 QQ ==========
            diary_preview = summary[:500] + ("..." if len(summary) > 500 else "")
            if NAPCAT_TARGET_USER:
                try:
                    result = await send_qq_message(int(NAPCAT_TARGET_USER), f"📔 昨日日记回顾:\n\n{diary_preview}", is_group=False, force_http=True)
                    if result is None:
                        print(f"❌ [DeepDream] QQ 发送日记失败")
                    else:
                        print(f"🌙 [DeepDream] 日记已同步推送至 QQ")
                except Exception as e:
                    print(f"❌ [DeepDream] 推送 QQ 失败: {e}")
            print(f"✅ 日记已生成并归档: 📅 昨日回溯: {yesterday}")
        else:
            print("⚠️ 日记生成失败（LLM 返回空），跳过后续宏观收束。")
            return

        # 清理 2 天前的低重要度记录（防止流水单调累积）
        try:
            def _clean_old():
                del_time = (now_bj - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
                supabase.table("memories").delete().lt("importance", 4).lt("created_at", del_time).execute()
            await asyncio.to_thread(_clean_old)
        except Exception as e:
            print(f"⚠️ 旧记忆清理失败（不影响日记）: {e}")

        # === 宏观记忆收束体系 ===

        # 1. 周度总结 (每周日触发)
        if now_bj.weekday() == 6:
            try:
                week_ago = (now_bj - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                week_res = await asyncio.to_thread(
                    lambda: supabase.table("memories").select("id, content").eq("tags", "Core_Cognition").gt("created_at", week_ago).execute()
                )
                if week_res.data and len(week_res.data) >= 3:
                    week_context = "\n".join([f"- {w['content']}" for w in week_res.data])
                    week_summary = await _ask_llm_async(
                        client,
                        f"【本周每日日记】:\n{week_context}\n\n请将这周的日记提炼成一篇深度的周度长期记忆总结。纯文本输出。",
                        temperature=0.7
                    )
                    if week_summary:
                        await asyncio.to_thread(
                            _save_memory_to_db, "📚 周度记忆沉淀", week_summary,
                            MemoryType.EMOTION, "温情", "Core_Cognition_Weekly"
                        )
                        await asyncio.to_thread(_send_email_helper, "📦 每周深度记忆归档", week_summary)
                        if NAPCAT_TARGET_USER:
                            try:
                                await send_qq_message(int(NAPCAT_TARGET_USER), f"📚 周度记忆沉淀:\n\n{week_summary[:500]}", is_group=False, force_http=True)
                            except Exception:
                                pass
                        print("✅ 周度记忆已沉淀。")
            except Exception as e:
                print(f"⚠️ 周度总结失败（不影响日记）: {e}")

        # 2. 月度总结 (每月最后一天触发)
        tomorrow = now_bj + datetime.timedelta(days=1)
        if tomorrow.day == 1:
            try:
                month_ago = (now_bj - datetime.timedelta(days=32)).strftime("%Y-%m-%d %H:%M:%S")
                month_res = await asyncio.to_thread(
                    lambda: supabase.table("memories").select("id, content").eq("tags", "Core_Cognition_Weekly").gt("created_at", month_ago).execute()
                )
                if month_res.data:
                    month_context = "\n".join([f"- {m['content']}" for m in month_res.data])
                    month_summary = await _ask_llm_async(
                        client,
                        f"【本月周度记忆】:\n{month_context}\n\n请以【{AI_NAME}】的第一人称视角，提炼本月的核心大事件与情感走向，生成一篇月度回忆录。纯文本输出。",
                        temperature=0.7
                    )
                    if month_summary:
                        await asyncio.to_thread(
                            _save_memory_to_db, "🌕 月度记忆沉淀", month_summary,
                            MemoryType.EMOTION, "感慨", "Core_Cognition_Monthly"
                        )
                        await asyncio.to_thread(_send_email_helper, "📦 每月深度记忆归档", month_summary)
                        if NAPCAT_TARGET_USER:
                            try:
                                await send_qq_message(int(NAPCAT_TARGET_USER), f"🌕 月度记忆沉淀:\n\n{month_summary[:500]}", is_group=False, force_http=True)
                            except Exception:
                                pass
                        # 阅后即焚：清理已归档的周总结
                        m_ids = [m['id'] for m in month_res.data]
                        await asyncio.to_thread(lambda: supabase.table("memories").delete().in_("id", m_ids).execute())
                        print(f"✅ 月度记忆已沉淀，清理 {len(m_ids)} 条历史周总结。")
            except Exception as e:
                print(f"⚠️ 月度总结失败（不影响日记）: {e}")

        # 3. 年度总结 (每年 12 月 31 日触发)
        if now_bj.month == 12 and now_bj.day == 31:
            try:
                year_ago = (now_bj - datetime.timedelta(days=366)).strftime("%Y-%m-%d %H:%M:%S")
                year_res = await asyncio.to_thread(
                    lambda: supabase.table("memories").select("id, content").eq("tags", "Core_Cognition_Monthly").gt("created_at", year_ago).execute()
                )
                if year_res.data:
                    year_context = "\n".join([f"- {y['content']}" for y in year_res.data])
                    year_summary = await _ask_llm_async(
                        client,
                        f"【本年度月度记忆】:\n{year_context}\n\n请总结这一年的点点滴滴，写一篇年度回忆录。纯文本输出。",
                        temperature=0.7
                    )
                    if year_summary:
                        await asyncio.to_thread(
                            _save_memory_to_db, "🌟 年度终极回忆录", year_summary,
                            MemoryType.EMOTION, "感动", "Core_Cognition_Yearly"
                        )
                        await asyncio.to_thread(_send_email_helper, "📦 年度终极记忆归档", year_summary)
                        if NAPCAT_TARGET_USER:
                            try:
                                await send_qq_message(int(NAPCAT_TARGET_USER), f"🌟 年度回忆录:\n\n{year_summary[:500]}", is_group=False, force_http=True)
                            except Exception:
                                pass
                        y_ids = [y['id'] for y in year_res.data]
                        await asyncio.to_thread(lambda: supabase.table("memories").delete().in_("id", y_ids).execute())
                        print(f"✅ 年度记忆已沉淀，清理 {len(y_ids)} 条历史月总结。")
            except Exception as e:
                print(f"⚠️ 年度总结失败（不影响日记）: {e}")

        print("✨ 深度睡眠完成，日记与宏观记忆已归档。")

    except Exception as e:
        print(f"❌ 深夜日记生成失败: {e}")


async def async_diary_worker():
    """
    📔 每日日记生成器：独立协程，到指定时间自动触发深度日记生成。
    - 启动时检查并补写昨日缺失的日记
    - 每天到 DIARY_TIME（默认凌晨3点）自动触发
    - 与主动问候循环解耦，互不干扰
    """
    from server import supabase

    print("📔 每日日记生成神经已上线...")
    diary_time = os.environ.get("DIARY_TIME", "03:00")
    last_run_date = ""

    # 启动时补写昨日日记（如果还没写过）
    try:
        if supabase:
            now_bj = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            yesterday = (now_bj - datetime.timedelta(days=1)).date()
            target_title = f"📅 昨日回溯: {yesterday}"
            def _check_diary():
                return supabase.table("memories").select("id").eq("title", target_title).execute().data
            exists = await asyncio.to_thread(_check_diary)
            if not exists:
                print(f"📝 检测到昨日日记缺失，立即补写: {target_title}")
                await _perform_deep_dreaming()
                last_run_date = now_bj.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"❌ 启动补写日记失败: {e}")

    while True:
        try:
            now_bj = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            current_hm = now_bj.strftime("%H:%M")
            current_date = now_bj.strftime("%Y-%m-%d")

            if current_hm == diary_time and last_run_date != current_date:
                last_run_date = current_date
                print(f"📔 [{current_hm}] 到达日记生成时间，启动深度睡眠...")
                await _perform_deep_dreaming()
        except Exception as e:
            print(f"❌ 日记生成器报错: {e}")

        # 对齐到下一分钟
        now = datetime.datetime.utcnow()
        sleep_sec = 60 - now.second + 1
        await asyncio.sleep(sleep_sec)


# ==========================================
# 🗑️ [已移除] Telegram 消息轮询
# ==========================================
# async def async_telegram_polling(): ... (Telegram Bot 轮询已移除，仅保留 QQ 通道)




# ==========================================
# 3. 消息总结器
# ==========================================

async def async_message_summarizer():
    """定期汇总数据库中未处理的消息，避免打扰用户。"""
    from server import _get_llm_client, _ask_llm_async, _push_wechat, _save_memory_to_db, supabase

    print("📋 消息总结器已上线...")
    # 总结间隔（秒），默认半小时
    interval = int(os.environ.get("SUMMARIZE_INTERVAL", 1800))

    while True:
        await asyncio.sleep(interval)
        if not supabase:
            continue
        # 消息总结也是总结类，按用户要求统一用聊天模型（main_chat）
        client = _get_llm_client("main_chat")
        if not client:
            continue
        try:
            # 查出所有未总结的消息
            res = await asyncio.to_thread(
                lambda: supabase.table("memories").select("id, title, content")
                .eq("tags", "Pending").execute()
            )

            if res.data and len(res.data) > 0:
                msgs = "\n".join([f"{item['title']}: {item['content']}" for item in res.data])

                # 如果消息极少，直接标记已处理跳过
                if len(msgs) < 30:
                    ids = [item['id'] for item in res.data]
                    await asyncio.to_thread(
                        lambda: supabase.table("memories").update({"tags": "Done"}).in_("id", ids).execute()
                    )
                    continue

                prompt = f"""
                以下是过去一段时间收到的消息：
                {msgs}

                请用简洁的口吻总结重点 (150 字以内)。如果没有重要的事，告诉用户一切正常。
                """
                summary = await _ask_llm_async(client, prompt, temperature=0.7)

                if summary:
                    await asyncio.to_thread(_push_wechat, summary, "📋 消息总结")
                    # ========== 同步推送消息总结到 QQ ==========
                    if NAPCAT_TARGET_USER:
                        try:
                            result = await send_qq_message(int(NAPCAT_TARGET_USER), f"📋 {summary}", is_group=False, force_http=True)
                            if result is None:
                                print(f"❌ [Summarizer] QQ 发送失败")
                            else:
                                print(f"📋 [Summarizer] 消息总结已同步推送至 QQ")
                        except Exception as e:
                            print(f"❌ [Summarizer] 推送 QQ 失败: {e}")
                    await asyncio.to_thread(
                        _save_memory_to_db, "🤖 互动记录",
                        f"发送了消息总结: {summary}", "流水", "尽责", "Summary"
                    )
                    ids = [item['id'] for item in res.data]
                    await asyncio.to_thread(
                        lambda: supabase.table("memories").update({"tags": "Done"}).in_("id", ids).execute()
                    )
        except Exception as e:
            print(f"❌ 消息总结器报错: {e}")


# ==========================================
# 🗑️ [已移除] 提醒巡视器
# ==========================================
# async def async_reminder_worker(): ... (提醒巡视器已移除，manage_reminder 功能已下线)




# ==========================================
# 🗑️ [已移除] 日程小秘书 + 日程播报
# ==========================================
# async def async_schedule_secretary(): ... (日历日程播报已移除)
# async def _broadcast_schedule(...): ... (日程播报辅助函数已移除)




# ==========================================
# 🗑️ [已移除] 信箱巡视器 (邮件)
# ==========================================
# async def async_email_secretary(): ... (信箱巡视器已移除，Gmail 收信功能已下线)




# ==========================================
# 7. 环境变量热同步
# ==========================================

async def async_env_sync():
    """定时从数据库 user_facts.sys_config 读取配置，热更新到环境变量。"""
    from server import supabase, ORIGINAL_ENV

    print("⚙️ 环境变量热同步神经已上线...")
    # 支持热同步的键列表 (可通过环境变量扩展)
    default_sync_keys = [
        "DEFAULT_API_KEY", "DEFAULT_BASE_URL", "DEFAULT_MODEL_NAME",
        "TG_BOT_TOKEN", "TG_CHAT_ID",
        "EMAIL_API_KEY", "EMAIL_FROM", "ADMIN_EMAIL",
        "AI_PERSONA", "MEM0_USER_ID",
    ]
    extra_keys = [k.strip() for k in os.environ.get("SYNC_KEYS", "").split(",") if k.strip()]
    sync_keys = list(set(default_sync_keys + extra_keys))

    while True:
        try:
            if supabase:
                def _sync():
                    res = supabase.table("user_facts").select("value").eq("key", "sys_config").execute()
                    if res.data:
                        conf = json.loads(res.data[0]['value'])
                        for k in sync_keys:
                            val = str(conf.get(k, "")).strip()
                            if val:
                                os.environ[k] = val
                            else:
                                if k in ORIGINAL_ENV:
                                    os.environ[k] = ORIGINAL_ENV[k]
                                elif k in os.environ:
                                    del os.environ[k]
                await asyncio.to_thread(_sync)
        except Exception:
            pass
        await asyncio.sleep(10)


# ==========================================
# 8. 启动入口
# ==========================================

def start_autonomous_life():
    """启动所有后台心跳线程 (daemon 模式，主进程退出时自动结束)。"""
    def _run_heartbeat(): asyncio.run(async_autonomous_life())
    def _run_diary(): asyncio.run(async_diary_worker())
    # 🗑️ [已移除] Telegram 轮询、提醒巡视器、日程秘书、信箱巡视器
    def _run_msg_sum(): asyncio.run(async_message_summarizer())
    def _run_env_sync(): asyncio.run(async_env_sync())

    threading.Thread(target=_run_env_sync, daemon=True).start()
    threading.Thread(target=_run_heartbeat, daemon=True).start()
    threading.Thread(target=_run_diary, daemon=True).start()
    threading.Thread(target=_run_msg_sum, daemon=True).start()

    print("🐱 NapCat QQ 端点已就绪 (被动模式)，等待本地 NapCat 通过反向 WS 连接...")
    print("🌾 后台心跳线程已启动 (自主生命 / 日记生成 / 消息总结 / 环境同步)。")
