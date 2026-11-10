FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY docuteam/sandbox/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY runner/server.py /srv/server.py
RUN useradd -m -u 1000 runner && mkdir /work && chown runner /work
USER runner
WORKDIR /work
ENV HOST=0.0.0.0 PORT=9000 WORKDIR=/work
CMD ["python", "/srv/server.py"]
