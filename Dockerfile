FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m learner
COPY app app
COPY courses courses
USER learner
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790", "--no-proxy-headers"]
