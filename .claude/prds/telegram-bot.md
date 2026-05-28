# PRD — Telegram Bot bidirectionnel

**Date:** 2026-05-28
**Phase:** 2
**Spec:** `docs/specs/2026-05-28-telegram-bot-design.md`

---

## Problème

ChatGPT Radio tourne 24/7 sans supervision. Quand le stream crashe la nuit, il n'y a aucune notification — le downtime est découvert manuellement. Il faut un canal d'alerte mobile fiable et un moyen de relancer sans SSH.

## Hypothèse

Un bot Telegram tournant comme service systemd indépendant, lisant GlobalState via WebSocket, permettra de détecter les crashs (disconnect WebSocket) et de relancer le stream depuis un téléphone en < 30 secondes.

## Scope

**In :**
- `telegram_bot.py` — processus autonome (hors main.py)
- Alertes : stream DOWN/UP (WebSocket disconnect/reconnect), debounce 30s
- Commandes : `/status`, `/music`, `/viewers`, `/health`, `/restart`
- Allowlist `TELEGRAM_CHAT_ID` — usage privé mono-utilisateur
- Service systemd `chatgpt-radio-tg.service`, `Restart=always`
- Tests unitaires (mocks PTB + WebSocket)

**Out :**
- Notifications de changement de track
- Commandes audio (skip, territoire)
- Multi-utilisateurs / permissions
- Webhook Telegram

## Critères de succès

1. Stream DOWN détecté en < 35s (30s debounce + délai WebSocket)
2. `/restart` lance `scripts/restart.sh` sans injection shell, confirme avec log
3. Toute commande d'un chat_id non autorisé ignorée silencieusement
4. Bot relancé automatiquement par systemd après crash
5. Tests ≥ 80% coverage sur `telegram_bot.py`
