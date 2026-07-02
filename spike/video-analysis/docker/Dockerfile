# Phase 0 spike image — runs run_spike.py on ACA serverless GPU (T4).
# Build from spike/video-analysis/:  az acr build -r acrloanarmy -f docker/Dockerfile -t video-spike:v1 .
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docker/requirements-docker.txt .
# torch from PyPI ships CUDA support on linux/amd64; the ACA GPU profile provides the driver.
RUN pip install --no-cache-dir -r requirements-docker.txt
# Fail the BUILD (with the real traceback) if any runtime import is broken.
RUN python -c "import torch, cv2, av, supervision, trackers, transformers, umap, sklearn; print('imports OK')"

COPY run_spike.py merge_tracklets.py ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
