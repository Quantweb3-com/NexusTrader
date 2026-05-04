FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY . .

RUN pip install --no-cache-dir .
