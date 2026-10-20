FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user && mkdir -p /home/user/app && chown -R user:user /home/user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface PYTHONUNBUFFERED=1
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p models && python -m piper.download_voices en_US-lessac-medium --download-dir models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
COPY --chown=user . .
RUN mkdir -p data
ENV DATA_DIR=/home/user/app/data PIPER_MODEL=models/en_US-lessac-medium.onnx
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]