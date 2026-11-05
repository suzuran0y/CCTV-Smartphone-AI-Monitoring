FROM python:3.11-slim

# 安装 OpenCV 和 FFmpeg 必须的底层系统依赖 (使用新版 Debian 的包名)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 设置容器内的工作目录
WORKDIR /app

# 优先拷贝 requirements.txt，利用 Docker 缓存机制加速后续构建
COPY requirements.txt .

# 安装 Python 依赖包
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录下的所有代码拷贝到容器的 /app 目录下
COPY . .

# 启动命令 (假设项目的主入口是 server.py，如果是其他名字请自行修改)
CMD ["python", "server.py"]