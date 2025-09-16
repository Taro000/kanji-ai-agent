FROM python:3.11-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    gcc \
    g++ \
    make \
    cmake

# uvのインストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .