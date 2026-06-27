# ==========================================
# 通用 MCP 网关 Dockerfile
# ==========================================
# 基础镜像：python:3.11-slim (体积小，生产可用)
FROM python:3.11-slim

# 设置时区为北京时间 (与代码中的 _get_now_bj 一致)
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 先复制依赖清单，利用 Docker 缓存层加速构建
COPY requirements.txt .

# 安装系统依赖 (部分 Python 包需要编译) + Python 依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制项目源码
COPY server.py gateway.py heartbeat.py napcat.py ./

# 暴露端口 (云平台通过 PORT 环境变量覆盖)
ENV PORT=10000
EXPOSE 10000

# 健康检查 (容器编排平台可用)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health', timeout=5)" || exit 1

# 启动命令
CMD ["python", "server.py"]