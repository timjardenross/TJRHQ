#!/usr/bin/env bash
# Listen for the first private message to the bot, capture its chat id,
# write it into .env, and restart the service. Self-healing: always
# restarts the service on exit even if no message arrives.
set -u
DIR=/opt/starship-endeavour/telegram-bot
ENV="$DIR/.env"
TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2-)
SVC=telegram-chief-engineer.service
DEADLINE=$(( $(date +%s) + 1800 ))   # 30 minutes
OFFSET=0

restart_svc() { systemctl start "$SVC"; }
trap restart_svc EXIT

# Free the poller lock so we can read updates ourselves.
systemctl stop "$SVC"
sleep 1

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  RESP=$(curl -s --max-time 35 "https://api.telegram.org/bot${TOKEN}/getUpdates?timeout=30&offset=${OFFSET}")
  CID=$(printf '%s' "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
res=d.get('result',[]) if d.get('ok') else []
if res:
    print('OFFSET', res[-1]['update_id']+1)
for u in res:
    m=u.get('message') or u.get('edited_message') or {}
    ch=m.get('chat') or {}
    if ch.get('type')=='private' and ch.get('id') is not None:
        print('CHATID', ch['id'], ch.get('username') or ch.get('first_name') or '')
        break
")
  NEWOFF=$(printf '%s' "$CID" | awk '/^OFFSET/{print $2}')
  [ -n "$NEWOFF" ] && OFFSET="$NEWOFF"
  FOUND=$(printf '%s' "$CID" | awk '/^CHATID/{print $2; exit}')
  if [ -n "$FOUND" ]; then
    NAME=$(printf '%s' "$CID" | awk '/^CHATID/{print $3; exit}')
    sed -i -E "s/^TELEGRAM_ALLOWED_CHAT_IDS=.*/TELEGRAM_ALLOWED_CHAT_IDS=${FOUND}/" "$ENV"
    echo "DETECTED chat_id=${FOUND} name=${NAME} -> written to .env"
    exit 0   # trap restarts the service with the new id
  fi
done
echo "TIMEOUT: no private message received in 20 min; service restarted unchanged."
