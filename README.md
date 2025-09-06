# Engineer Personal Messenger Bot (Telegram)

A privacy-first, admin-routed messenger bot. Users message the bot; messages are delivered to the admin. The admin replies anonymously via the bot. Includes admin tools (ban/unban, who, stats) and personal utilities (notes, tasks, reminders, export, file vault).

## Highlights
- Private routing: user → bot → admin; admin reply → bot → user.
- Anonymous replies: admin identity stays hidden to users.
- Admin keyboard: normal reply keyboard for quick actions (Reply, Who, Ban, Unban, Quick Replies, Cancel).
- User registry: tracks users with last_seen and basic profile.
- Moderation: ban/unban via buttons or commands.
- Utilities (admin-only): notes, tasks, reminders, search, export, file vault.
- SQLite storage: simple, portable, WAL-enabled.

## Quickstart
- Create `.env`:
  - `cp .env.example .env` and set `BOT_TOKEN` and `ADMIN_ID` (numeric).
- Install:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Run:
  - `python -m bot.main`

## Environment
- `BOT_TOKEN`: bot token from @BotFather.
- `ADMIN_ID`: your numeric Telegram user id.
- `ALLOWED_USER_IDS`: optional comma-separated ids; defaults to `{ADMIN_ID}`.
- `DB_PATH`: SQLite path; default `data/bot.db`.

## User Flow
- Users: send any message to the bot; it will be forwarded to the admin. They receive a confirmation and later the admin’s anonymous reply.
- Admin: receives user messages with a normal keyboard showing actions for that user id.
  - Reply paths:
    - Reply to the delivered message directly; or
    - Press `Reply <id>` then send your message (reply mode stays until `Cancel`).
  - Quick Replies: prefilled short answers (`QR: ...`).
  - Links: `Open Profile`/`Open DM` appear as URLs in message text or can be followed from the client.

## Admin Commands (DM with the bot)
- `/ban <user_id> [reason]`: ban a user.
- `/unban <user_id>`: unban a user.
- `/who <user_id>`: show user info and ban status.
- `/stats`: counts of users, bans, and messages.
- Notes & Tasks: `/note`, `/notes`, `/delnote`, `/task`, `/tasks`, `/done`, `/deltask`.
- Reminders: `/remind in 10m <text>` or `at YYYY-MM-DD HH:MM <text>`, `/reminders`, `/delrem`.
- Search & Export: `/search <query>`, `/export notes|tasks`.

## Data Model (SQLite)
- `users(user_id, first_name, last_name, username, language_code, is_bot, last_seen)`
- `bans(user_id, reason, active, created_at, updated_at)`
- `relays(id, user_id, direction, admin_msg_id, peer_msg_id, created_at)`
- `messages(id, user_id, text, created_at)`
- `notes(id, user_id, text, created_at)`
- `tasks(id, user_id, text, done, created_at, done_at)`
- `reminders(id, user_id, text, due_ts, status, created_at)`
- `files(id, user_id, file_id, unique_id, kind, caption, created_at)`

## Security
- Never commit real secrets. `.env` is gitignored. `.env.example` uses placeholders.
- Rotate leaked tokens immediately using @BotFather.
- Access is restricted to admin for management commands and utilities.

## Deploy & Run
- Local: see Quickstart.
- Server: use a process supervisor (systemd, pm2, docker) or run as service.
  - Example systemd service: set `WorkingDirectory` to the repo and `ExecStart` to `.../python -m bot.main`.

## GitHub Launch Checklist
- Sanitize sample env: done in `.env.example`.
- Ignore secrets and local data: see `.gitignore`.
- Clear README with setup, usage, features: this file.
- Optional: add a license if you intend to open source.

## Roadmap Ideas
- Advanced anti-spam (rate limiting per chat window, flood control).
- Reply templates management (add/remove templates at runtime).
- FTS5 search over messages/notes/tasks.
- Conversation grouping per user (ticket/thread IDs).
- Multi-admin support with per-admin permissions.
