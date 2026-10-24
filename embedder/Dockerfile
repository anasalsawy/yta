FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false MODEL_PATH=/opt/model HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install sentence-transformers==6.2.0 transformers==5.20.2 soundfile==0.14.0 scipy==1.17.1 pillow
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('google/embeddinggemma-2', local_dir='/opt/model', ignore_patterns=['*.onnx','*.tflite','*.gguf','*.h5','*.msgpack'])"
WORKDIR /app
COPY embedder/server.py /app/server.py
EXPOSE 10000
CMD ["python", "server.py"]
