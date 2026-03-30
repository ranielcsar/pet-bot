FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Apenas as dependências essenciais
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY events_cog.py main.py ./

# Cria diretório data e ajusta permissões
RUN mkdir -p /app/data && \
    adduser --disabled-password --gecos "" botuser && \
    chown -R botuser:botuser /app

USER botuser

# Comando simples para rodar o bot
CMD ["python", "main.py"]