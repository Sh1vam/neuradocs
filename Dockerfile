FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# CPU-only torch first: the default PyPI wheel on Linux is the multi-GB CUDA build
COPY constraints.txt requirements.txt ./
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu -c constraints.txt \
 && pip install -r requirements.txt -c constraints.txt
COPY . .
# the models are downloaded while the image is built, so a running container needs no internet for them
RUN python docuteam/download_models.py
RUN useradd -m -u 1000 app && mkdir -p /data /app/docuteam/chroma /app/outputs && chown -R app:app /app /data
USER app
ENV HOST=0.0.0.0 PORT=8001 NEURACHAT_DB=/data/neurachat.db
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8001')+'/api/health')"
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
