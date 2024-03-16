FROM python:3.11

RUN apt-get update && apt-get install -y \
    ffmpeg --fix-missing \
    && rm -rf /var/lib/apt/lists/*

WORKDIR .
COPY . .

# RUN python3.11 -m venv ./venv
# RUN venv/bin/pip install -r requirements.txt

WORKDIR /src
