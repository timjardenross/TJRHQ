# USS TJR Control Deck

Local macOS developer operations launcher for USS TJR.

The Control Deck manages one tmux session named `usstjr` with five panes:

1. Slack Bot
2. Commander
3. Paperclip
4. Health Monitor
5. NGROK Tunnel

This is not a production deployment system. It only manages the `usstjr` tmux session and does not kill unrelated processes.

## Requirements

- macOS Terminal or iTerm2
- `tmux`
- Optional: `ngrok`, `jq`, `btop` or `htop`

Install common tools with Homebrew:

```bash
brew install tmux jq btop
```

Install and authenticate ngrok separately if needed:

```bash
ngrok config add-authtoken <token>
```

Do not store ngrok tokens or other secrets in this repository.

## Configure Services

Edit:

```bash
USS-TJR-Control/config/services.conf
```

Update paths and commands once local service locations are stable:

```bash
SLACK_BOT_DIR="$HOME/USSTJROS/slack-bot"
COMMANDER_DIR="$HOME/USSTJROS"
PAPERCLIP_DIR="$HOME/.paperclip"

SLACK_BOT_COMMAND="python3 app.py"
COMMANDER_COMMAND="python3 commander.py"
PAPERCLIP_COMMAND="paperclip"
NGROK_COMMAND="ngrok http ${NGROK_PORT}"
```

If a configured directory is missing, the pane prints a helpful message and stays open.

## Commands

Start or attach to the Control Deck:

```bash
./start.command
```

Stop only the `usstjr` tmux session:

```bash
./stop.command
```

Restart only the `usstjr` tmux session:

```bash
./restart.command
```

Show local environment status:

```bash
./status.command
```

## Finder Usage

The `.command` files are executable macOS launchers. Double-click `start.command` in Finder to launch the Control Deck in Terminal.

## Logs

Logs are written under:

```bash
USS-TJR-Control/logs/
```

Files:

- `slack-bot.log`
- `commander.log`
- `paperclip.log`
- `health-monitor.log`
- `ngrok.log`

## Pane Layout

The tmux script creates a tiled layout and labels pane borders:

- Slack Bot
- Commander
- Paperclip
- Health Monitor
- NGROK Tunnel

If the session already exists, `start.command` attaches to it instead of creating a duplicate.

## Safety

The Control Deck does not:

- Store tokens
- Hard-code secrets
- Kill unrelated tmux sessions
- Kill unrelated Python or Node processes
- Assume all services are installed
- Assume configured paths are correct

Only the tmux session named `usstjr` is controlled.
