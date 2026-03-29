app = "pet-bot"

primary_region = "gru"

build = "."

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1

[env]
  TZ = "America/Sao_Paulo"

[mounts]
  source = "data"
  destination = "/app/data"

[experimental]
  cmd = ["python", "main.py"]

# Sem health check - o Fly.io só mantém o processo rodando