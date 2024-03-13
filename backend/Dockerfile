FROM python:3.11

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR .
COPY . .

RUN python3.11 -m venv ./venv
RUN venv/bin/pip install -r requirements.txt
WORKDIR /src