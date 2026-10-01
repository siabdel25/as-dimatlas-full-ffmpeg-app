FROM python:3.13-slim

# ffmpeg/ffprobe : dépendance système principale. nodejs : solveur JS de
# yt-dlp pour YouTube (utilisé quand deno est absent).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static/ static/

# Dossiers de travail montés en volumes par docker-compose
RUN mkdir -p downloads audio cookies

EXPOSE 5000
ENV HOST=0.0.0.0
# Cookies YouTube (anti-bot) : fichier optionnel déposé dans le volume cookies/
ENV YT_COOKIES_FILE=/app/cookies/cookies.txt

CMD ["python", "app.py"]
