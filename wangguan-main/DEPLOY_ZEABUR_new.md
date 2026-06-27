# 🍼 Zeabur 部署宝宝级教程（零基础也能跟着做）

> 这是一份**假设你什么都不懂**的教程。每一步都写清楚"点哪里、填什么、看到什么算成功"。
> 只要你会用浏览器和复制粘贴，就能跟着做下来。
>
> ⏱ 全程大约 30 分钟。别急，慢慢来。

---

## 🤔 先搞懂我们在干什么

**我们要做的事，用大白话说就是：**

把这套"AI 工具网关"代码，放到一台**永远在线、别人也能访问**的电脑（服务器）上跑起来。这样你的 Claude、Cursor 等 AI 工具，就能随时调用它提供的 30 多个功能（比如记忆、搜索、发消息）。

**为什么要用 Zeabur？**

| 自己买服务器 | 用 Zeabur |
|:---:|:---:|
| 要花钱、要配置、要懂 Linux | 注册就能用，有免费额度 |
| 要自己搞 HTTPS 证书 | 自动给你 HTTPS |
| 要自己开机、防断电 | 24 小时有人帮你看着 |

简单说：**Zeabur 就像"AI 应用的托儿所"，你把代码交给他，他帮你养着。**

---

## 📋 开始前，你需要准备的东西

只有 1 样是**必须**的，其他都是"有了更好，没有也能跑"。

### 🔴 必须（没有这个跑不起来）

| 要什么 | 是什么 | 怎么拿 |
|--------|--------|--------|
| **一个 AI 的"钥匙"**（API Key） | 让程序能调用 AI 大模型的密码 | 看下面👇的详细说明 |

#### 🔑 怎么拿到 AI 的"钥匙"（3 选 1 即可）

**选 A：用 OpenAI（ChatGPT 那家，要美元，但最标准）**
1. 打开 https://platform.openai.com/
2. 注册登录（可能需要国外手机号）
3. 点右上角头像 → `View API keys`
4. 点 `Create new secret key` → 复制那串 `sk-...` → 这就是你的 `OPENAI_API_KEY`

**选 B：用 DeepSeek（国产，便宜，中文友好，推荐新手）**
1. 打开 https://platform.deepseek.com/
2. 手机号注册登录
3. 左边菜单点 `API keys` → `创建 API Key`
4. 复制那串 `sk-...` → 这就是你的 `OPENAI_API_KEY`
5. 记住模型名是 `deepseek-chat`

**选 C：用硅基流动 SiliconFlow（国产聚合平台，模型多，有免费额度）**
1. 打开 https://siliconflow.cn/
2. 注册登录
3. 左边点 `API 密钥` → `新建密钥`
4. 复制那串 `sk-...` → 这就是你的 `OPENAI_API_KEY`
5. 记住 Base URL 是 `https://api.siliconflow.cn/v1`

> 💡 **不知道选哪个？新手就选 DeepSeek**，便宜好用，注册送钱。

---

### 🟡 有了更好（可以稍后再加，先跳过也行）

| 要什么 | 用来干嘛 | 怎么拿 |
|--------|---------|--------|
| GitHub 账号 | 存放你的代码 | https://github.com 注册（免费） |
| Supabase 账号 | 给 AI 配个"记忆数据库" | https://supabase.com 注册（有免费额度） |
| Telegram 账号 | 让 AI 能给你发消息 | 手机装 Telegram App |

> 🧸 **宝宝建议**：第一次部署，**先把必须的搞定，跑通了再说**。那些"有了更好"的东西，等你成功部署一次后，再回来一个个加，心里有底。

---

## 🎯 第一步：把代码放到 GitHub 上

Zeabur 不能直接读你电脑上的文件，得先把代码放到 GitHub（一个"代码网盘"），然后让 Zeabur 去 GitHub 取。

### 1.1 注册 GitHub（已有账号跳过）

1. 打开 https://github.com/
2. 右上角点 `Sign up`
3. 填邮箱、设密码、取用户名 → 完成验证 → 注册

### 1.2 在 GitHub 上创建一个"仓库"（放代码的文件夹）

1. 登录后，右上角点 **`+`** → 选 `New repository`
2. 照着填：
   - **Repository name**（仓库名）：填 `mcp-gateway`（名字随便起，这个最直观）
   - **Description**（描述，可填可不填）：`我的 AI 网关`
   - **Public 还是 Private**：选 **Private**（私有，别人看不到你的代码，更安全）
   - 底下那个 `Add a README file`：**勾上**（这样仓库不会是空的）
3. 点绿色的 **`Create repository`** 按钮

✅ **看到什么算成功**：页面跳转，显示你的仓库 `你的用户名/mcp-gateway`，里面有一个 README 文件。

### 1.3 把本项目的代码传上去（最简单的方法：网页上传）

1. 把 `c:\Users\diant\Desktop\mcp-gateway-main` 文件夹打开
2. **选中所有文件**，除了这几个别传：
   - ❌ `.env`（如果有的话，这是你的私人密钥，绝不能传！）
   - ❌ `__pycache__` 文件夹（缓存垃圾）
3. 回到 GitHub 你的仓库页面
4. 点 **`Add file`** → **`Upload files`**
5. 把刚才选中的文件**拖进**那个虚线框里
6. 等它上传完（每个文件前面会出现绿色对勾）
7. 滚到页面最下面，点绿色的 **`Commit changes`** 按钮

✅ **看到什么算成功**：你的仓库里能看到 `server.py`、`gateway.py`、`Dockerfile` 这些文件。

> ⚠️ **重要！** 千万别传 `.env` 文件！里面有你的密钥，传上去等于把家门钥匙挂门外了。
> （项目里的 `.gitignore` 已经帮你挡住了，但网页上传时你还是手动确认下比较保险）

---

## 🚀 第二步：在 Zeabur 创建项目

### 2.1 注册 Zeabur

1. 打开 https://zeabur.com/
2. 点右上角 `Login`（登录）
3. 点 **`Login with GitHub`**（用 GitHub 登录，省得再注册一个号）
4. 弹出 GitHub 授权页面 → 点 **`Authorize Zeabur`**（同意授权）
5. 完成登录

### 2.2 新建一个项目

1. 进入 https://dashboard.zeabur.com （控制台）
2. 点 **`+ New Project`**（新建项目）
3. 项目名填 `mcp-gateway`（或者随你喜好）
4. **Region**（地区）：选离你近的，比如 `Asia - Hong Kong`（亚洲-香港）
5. 点 **`Create`**（创建）

✅ **看到什么算成功**：进入一个空的项目页面，提示你添加服务。

### 2.3 把 GitHub 代码连进来

1. 在项目页面点 **`+ Add Service`**（添加服务）
2. 选 **`Git Repository`**（Git 仓库）
3. 第一次会让你授权，点 **`Configure GitHub`**，按提示授权（可以只授权刚才那个仓库）
4. 列表里会出现你 GitHub 的仓库 → 点 **`mcp-gateway`**

✅ **看到什么算成功**：Zeabur 开始自动构建（你会看到一堆滚动的英文日志，那是它在装依赖，正常现象）。

### 2.4 等它构建完（喝杯水的时间）

- 构建大概要 **2~5 分钟**
- 你会看到状态从 `Building`（构建中）→ `Running`（运行中，变绿色）
- **⚠️ 注意：此刻虽然"运行中"了，但还没配钥匙（环境变量），还不能用，继续下一步！**

> 💡 如果卡了 10 分钟还没动静，或者红色报错了，往下翻到「🆘 我卡住了」章节。

---

## 🔑 第三步：配置"钥匙"（环境变量）

**这是最关键的一步！** 想象 Zeabur 是个新员工，代码已经给他了，但他还不知道 Wi-Fi 密码（API Key），所以啥也干不了。我们要把"密码"告诉他。

### 3.1 找到填密码的地方

1. 在 Zeabur 你的服务（`mcp-gateway`）卡片上**点一下**，进入详情
2. 上方有一排标签，点 **`Variables`**（变量）
3. 右边有个 **`Edit`**（编辑）或 **`RAW Editor`**（原始编辑器）按钮，点它

### 3.2 填入最少的必填项（先让它能跑）

**如果你用的是 DeepSeek**，把下面这段复制到 RAW 编辑器（注意把 `你的DeepSeek密钥` 换成你真正的 key）：

```
OPENAI_API_KEY=你的DeepSeek密钥
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL_NAME=deepseek-chat
API_SECRET=随便打一串字母数字当密码比如abc123xyz
```

**如果你用的是 OpenAI**，填这个：

```
OPENAI_API_KEY=你的OpenAI密钥sk-xxxx
OPENAI_MODEL_NAME=gpt-4o-mini
API_SECRET=随便打一串字母数字当密码比如abc123xyz
```

**如果你用的是硅基流动 SiliconFlow**，填这个：

```
OPENAI_API_KEY=你的硅基流动密钥
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
API_SECRET=随便打一串字母数字当密码比如abc123xyz
```

> 🧸 **宝宝解释**：
> - `OPENAI_API_KEY` = 你的 AI 钥匙（虽然是这个变量名，但填 DeepSeek 的 key 也行，程序只认格式）
> - `OPENAI_BASE_URL` = 告诉程序"去哪家公司问"，DeepSeek/硅基流动要填，OpenAI 不用填（默认就是它）
> - `OPENAI_MODEL_NAME` = 用哪个 AI 模型
> - `API_SECRET` = 你自己设的管理密码，**记住它**，以后改设置要用

### 3.3 保存

1. 填完后点 **`Save`**（保存）
2. Zeabur 会**自动重新部署**（因为它检测到你改了密码）
3. 等 1~2 分钟，状态再次变绿 `Running`

✅ **看到什么算成功**：状态绿色 Running，且 Variables 里能看到你刚才填的几行。

---

## 🌐 第四步：给网关一个"网址"

现在网关跑起来了，但还没个"门牌号"，外面的 AI 工具找不到它。我们要向 Zeabur 要一个网址。

### 4.1 生成免费域名

1. 在服务详情页，点上方 **`Networking`**（网络）标签
2. 点 **`Generate Domain`**（生成域名）
3. Zeabur 会给你一个形如 `mcp-gateway-xxxxx.zeabur.app` 的网址
4. **把这个网址记下来！**（选中复制，存到记事本里）

✅ **看到什么算成功**：Networking 标签下显示一个绿色的网址，前面有 `https://`。

> 💡 **什么是域名？** 就是网址。就像你家有地址，别人才能找到你。Zeabur 免费送你一个，长这样 `xxx.zeabur.app`，自带 HTTPS（安全锁🔒），直接能用。

### 4.2 确认端口对不对

在同一个 `Networking` 页面，确认：

| 设置项 | 应该是 |
|--------|--------|
| Port（端口） | `10000` |

通常 Zeabur 会自动读取（因为 Dockerfile 里写了 `EXPOSE 10000`），不用你管。但如果列表是空的，手动点 `Add Port` 填 `10000`。

---

## ✅ 第五步：检查是否成功！

### 5.1 健康检查（最简单的测试）

1. 打开浏览器
2. 在地址栏输入：`https://你的域名/health`
   - 比如：`https://mcp-gateway-xxxxx.zeabur.app/health`
3. 回车

✅ **看到什么算成功**：页面显示类似
```json
{"status": "ok", ...}
```
看到 `ok` 就说明你的网关活得好好的！🎉

❌ **如果打不开 / 报错**：看下面「🆘 我卡住了」。

### 5.2 看看启动报告（很有用）

1. 回到 Zeabur，点你的服务卡片进入详情
2. 点上方 **`Runtime`** 或 **`Logs`**（日志）标签
3. 往上滚，找到网关刚启动时打印的「配置体检报告」，长这样：

```
╔════════════════════════════════════════╗
║          🔍 配置体检报告                ║
╠════════════════════════════════════════╣
║ ✅ LLM (默认模型)    → deepseek-chat    ║
║ ❌ 数据库 (Supabase) → 未配置           ║
║ ❌ Telegram 推送     → 未配置           ║
║ ✅ 网页搜索 (DDG)    → 免费免配置       ║
║   ...                                  ║
╚════════════════════════════════════════╝
```

- ✅ = 这个功能已经能用了
- ❌ = 这个功能没配（不影响其他功能，需要时再配）

**这份报告是你以后排查问题的第一现场。** 哪个功能不工作，先来这里看是不是 ❌。

---

## 🔌 第六步：让 Claude / Cursor 用上你的网关

你的网关已经活在线上了！现在把它"插"到你的 AI 工具里。

### 6.1 接到 Claude Desktop

1. 找到 Claude 的配置文件：
   - **Windows**：按 `Win+R`，输入 `%APPDATA%\Claude` 回车，找到 `claude_desktop_config.json`
   - **Mac**：打开 Finder，按 `Cmd+Shift+G`，输入 `~/Library/Application Support/Claude/`，找到 `claude_desktop_config.json`
2. 用记事本打开它，改成这样（**把域名换成你自己的**）：

```json
{
  "mcpServers": {
    "my-gateway": {
      "url": "https://你的域名.zeabur.app/sse"
    }
  }
}
```

3. 保存，**完全退出 Claude**（不是关窗口，是右下角图标右键退出），再重新打开
4. 在 Claude 对话框输入：`用 echo 工具测试一下`
5. 如果 Claude 成功调用工具并返回结果，**恭喜你，成功了！🎉**

### 6.2 接到 Cursor

1. 打开 Cursor → 设置（Settings）→ 搜 `MCP`
2. 点 `Add new MCP Server`
3. 填：
   - Name：`my-gateway`
   - URL：`https://你的域名.zeabur.app/sse`
4. 保存，重启 Cursor

### 6.3 接到任何 MCP 客户端

只要支持 MCP 协议的工具，接入地址都是：
```
https://你的域名.zeabur.app/sse
```
（注意结尾的 `/sse` 不能少）

---

## 🆘 我卡住了！常见问题

### 问题 1：Zeabur 构建失败（红色报错）

**最可能的原因 + 解决：**

| 报错关键字 | 原因 | 怎么办 |
|-----------|------|--------|
| `Dockerfile not found` | 没传 Dockerfile | 回 GitHub 确认 `Dockerfile` 传上去了 |
| `pip install` 超时 | 网络抽风 | 点 `Redeploy` 重新部署，多试几次 |
| `Module not found` | 代码没传全 | 确认 `requirements.txt`、`server.py` 等都在 GitHub 上 |

---

### 问题 2：构建成功了，但马上 Crash / 一直重启

**99% 是环境变量没配或配错了。**

1. 进 `Runtime → Logs`，找最后一行报错
2. 常见报错：

| 报错 | 原因 | 解决 |
|------|------|------|
| `OPENAI_API_KEY not set` | 没配 API Key | 回第三步配好 |
| `key must be sk- format` | Key 格式不对 | 检查是不是复制时多了空格 |
| `Connection refused` / `port error` | 端口不对 | 确认 Networking 里 Port = 10000 |

---

### 问题 3：`/health` 能打开，但 Claude 连上后转圈不响应

这是 **SSE 被中间环节缓冲了**。

1. 确认你的网址是 `https://` 开头（不是 http）
2. Zeabur 原生支持 SSE，一般没问题
3. 如果你套了 Cloudflare 之类的 CDN，关掉它的缓存/buffering

---

### 问题 4：忘了 `API_SECRET` 怎么办？

没事，去 Zeabur → Variables → 改一个新的 → Save，会自动重新部署。

---

### 问题 5：我改了环境变量，但好像没生效

1. Zeabur 改完 Variables 一般会自动重新部署
2. 没自动的话，进服务详情 → 点 `Redeploy`（重新部署）按钮
3. 或者用 API 强制重启：
   ```
   浏览器/Postman 发 POST 请求到 https://你的域名/api/restart
   Header: X-API-Secret: 你的API_SECRET
   ```

---

### 问题 6：完全看不懂日志里的英文

日志里的英文主要是：
- `INFO` = 普通信息（正常）
- `WARNING` = 警告（注意一下）
- `ERROR` = 出错了（要处理）

找 `ERROR` 那几行，复制去翻译软件，或者发给我看。

---

## 🎁 进阶：跑通后，怎么加更多功能？

基础版跑通后，你可以**按需添加**下面的功能。**每加一个，就回 Zeabur → Variables 多填几行 → Save 重新部署**，不用改代码。

### 加数据库（让 AI 有记忆）—— 推荐！

1. 去 https://supabase.com 注册，新建项目
2. 在 `Settings → API` 拿到 `URL` 和 `anon key`
3. 在 Supabase 的 `SQL Editor` 跑建表语句（问我要，或看完整版教程的附录）
4. 回 Zeabur Variables 加：
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_KEY=你的anon_key
   ```

### 加 Telegram 推送（让 AI 给你发消息）

1. Telegram 找 `@BotFather` → 发 `/newbot` → 拿到 `TG_BOT_TOKEN`
2. 给你的 bot 发条消息，访问 `https://api.telegram.org/bot你的TOKEN/getUpdates`，记下 `chat.id`
3. 回 Zeabur 加：
   ```
   TG_BOT_TOKEN=你的token
   TG_CHAT_ID=你的chat_id
   ```

### 加网页搜索（默认免费版已有）

默认就用 DuckDuckGo（不用配置）。想要更高质量的搜索，去 https://tavily.com 拿 key，加：
```
TAVILY_API_KEY=tvly-xxxx
```

> 📚 **所有可加的功能和对应变量**，看项目根目录的 `VARIABLES.md`（完整变量清单）和 `DEPLOY_ZEABUR.md`（完整版教程）。

---

## 🧠 记住这几件事（贴在显示器上）

1. **我的网址是**：`https://_______________.zeabur.app`
2. **MCP 接入点是**：`https://_______________.zeabur.app/sse`（结尾别忘 `/sse`）
3. **健康检查是**：`https://_______________.zeabur.app/health`
4. **我的管理密码是**：`______________`（就是 `API_SECRET`，别外传）
5. **改了东西没生效**：Zeabur → `Redeploy`
6. **出问题先看哪里**：Zeabur → `Runtime → Logs` + 启动时的「配置体检报告」

---

## 🎉 恭喜你！

如果你走到了这一步，你已经拥有了一个：

- ✅ 24 小时在线的 AI 工具网关
- ✅ 自带 HTTPS 的访问网址
- ✅ 30+ 个可调用的 AI 工具（记忆、搜索、发消息...）
- ✅ 可以让 Claude、Cursor 等 AI 工具接入的"超级后端"

**第一次部署成功是最难的，以后改任何东西都是"改 Variables → Redeploy"两步走，你已经跨过最难的那道坎了！**

---

> 📚 想看更完整、更技术向的教程？看同目录的 [`DEPLOY_ZEABUR.md`](DEPLOY_ZEABUR.md)（完整版）
>
> 想查所有环境变量？看 [`VARIABLES.md`](VARIABLES.md)（变量清单）
>
> 想了解整个项目架构？看 [`README.md`](README.md)（项目总览）