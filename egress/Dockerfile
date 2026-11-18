FROM python:3.13-slim
COPY egress/proxy.py /srv/proxy.py
RUN useradd -m -u 1000 egress && \
    chown -R egress:egress /srv && \
    pip install --no-cache-dir aiohttp
USER egress
ENV PORT=3128 PYTHONUNBUFFERED=1
CMD ["python", "/srv/proxy.py"]
