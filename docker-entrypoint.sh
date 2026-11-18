#!/bin/sh
set -e
# 1. local models (a no-op when they are already in the image), 2. the document index, 3. the app
python -c "import local_models; local_models.ensure_all()" || echo "model download failed: open /models after the start"
if [ ! -f docuteam/chroma/chroma.sqlite3 ]; then
  python docuteam/cli.py ingest || echo "index build failed: /documents will not answer until you add a document"
fi
exec python run.py
