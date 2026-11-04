# b2q serve 镜像（infra-server.md「serve Docker 镜像部署方案」§1）
# 模型与数据走挂载卷，不进镜像；构建在服务器本地做，不推外部 registry。
FROM python:3.12-slim

WORKDIR /app
COPY book2qa /app/book2qa

RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" onnxruntime tokenizers numpy matplotlib && \
    pip install --no-cache-dir --no-deps /app/book2qa

RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

ENV B2Q_SERVE_PORT=8100
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=3)"]

CMD ["uvicorn", "book2qa.serve:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
