#!/bin/sh
set -e
# first start on an empty volume: build the document index from docuteam/workspace/docs
if [ ! -f docuteam/chroma/chroma.sqlite3 ]; then
  python docuteam/cli.py ingest || echo "index build failed: /documents will not answer until you add a document"
fi
exec python run.py
