FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev liblcms2-dev \
    libwebp-dev libharfbuzz-dev libfribidi-dev libtiff5-dev \
    gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root
RUN useradd -m -u 1000 waifu && chown -R waifu:waifu /app
USER waifu

EXPOSE 8443

CMD ["python", "-m", "bot"]
