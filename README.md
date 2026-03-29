# 🔔 Event Reminder Bot

Bot Discord para registrar eventos e enviar lembretes automáticos.

## Estrutura
```
event_reminder_bot/
├── main.py          # Entry point
├── events_cog.py    # Lógica principal (comandos + tasks)
└── requirements.txt
```

## Instalação
```bash
pip install -r requirements.txt
export DISCORD_TOKEN="seu_token_aqui"
python main.py
```

## Comandos (Slash)

| Comando | Descrição |
|---|---|
| `/evento adicionar` | Registra um novo evento |
| `/evento listar` | Lista todos os eventos ativos |
| `/evento remover` | Remove um evento pelo ID |
| `/evento testar` | Força envio imediato (para testes) |

## Lógica de Lembretes

- **Fora da semana do evento**: 1 lembrete por semana, toda semana no mesmo dia da semana do evento (às 09:00)
- **Na semana do evento**: 3 lembretes por dia (08:00 · 14:00 · 20:00)
- **Após a data**: removido automaticamente

## Fuso Horário
Altere `TIMEZONE` em `events_cog.py`:
```python
TIMEZONE = zoneinfo.ZoneInfo("America/Sao_Paulo")
```
