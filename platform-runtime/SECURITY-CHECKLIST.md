# Security Checklist

## Secrets Management

Never commit:
- OPENAI_API_KEY
- SLACK_APP_TOKEN
- SLACK_BOT_TOKEN

Use:
- .env
- .gitignore

## Repository Security

Review:
- Public repositories
- Shared screenshots
- Logs

## Logging Controls

Do not log:
- API keys
- Tokens
- Credentials

Allowed:
- Mission IDs
- Status
- Routing decisions

## Access Control

Captain TJR retains authority.
Specialists provide recommendations only.

## Future Integrations

Before adding:
- Supabase
- Notion
- Voice Services

Review:
- Authentication
- Data storage
- Privacy impact

## Security Review Trigger

Perform review when:
- New integration added
- New AI model added
- Repository becomes public
- Memory layer introduced
