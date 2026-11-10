# Build once, with internet, from the project folder:
#   docker build -t agent-sandbox:latest -f sandbox/Dockerfile sandbox
FROM python:3.13-slim
RUN useradd -m agent
WORKDIR /work
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
USER agent
CMD ["sleep", "infinity"]
