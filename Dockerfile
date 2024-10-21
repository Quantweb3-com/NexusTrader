FROM python:3.11-slim-bullseye

RUN pip install --no-cache-dir --upgrade pip
# 安装 git 和 build-essential
RUN apt-get update && apt-get install -y \
    bash\
    nano \
    git \
    npm \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN npm install pm2 -g

WORKDIR /app

RUN git clone git@github.com:RiverTrading/tradebot-pro.git

WORKDIR /app/tradebot

RUN mkdir .keys && \
    touch .keys/config.cfg 

RUN pip install --no-cache-dir -r requirements.txt
