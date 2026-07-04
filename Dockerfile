FROM python:3.13-slim

# ffmpeg/ffprobe : la seule dépendance système de l'app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static/ static/

# Dossiers de travail montés en volumes par docker-compose
RUN mkdir -p downloads audio

EXPOSE 5000
ENV HOST=0.0.0.0

CMD ["python", "app.py"]
