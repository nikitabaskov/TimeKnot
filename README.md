# TimeKnot

A single-user Russian-language Telegram task and reminder assistant. Free-form messages are
parsed by an LLM into tasks; reminders fire through APScheduler and survive a restart because the
SQLite `tasks` table, not the scheduler, is the source of truth.

Local development lives in `CLAUDE.md`; this file is about running it on a server.

## Before you start: the bot needs outbound IPv4

`api.telegram.org` publishes **no AAAA record**. On an IPv6-only VPS the bot cannot reach Telegram
at all, and neither can `git clone` from GitHub, which is also IPv4-only. Check on the server:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.telegram.org
```

`200` (or `302`/`404` — anything but a connection error) means egress works and you can ignore the
rest of this section. A hang or `Could not resolve host` / `Network is unreachable` means it does
not. Four ways out:

1. **Buy an IPv4 address from the provider.** Usually a euro or two a month, and nothing else in
   this document changes. The boring answer, and the one with the fewest moving parts.
2. **Put the Cloudflare Worker relay in front of Telegram** — see the next section. Free, entirely
   under your own account, and the only thing it changes on the server is one environment
   variable. This does not give the box general IPv4; it fixes Telegram specifically, which is the
   only host that needs it at runtime.
3. **Use the provider's NAT64/DNS64**, if it has one. Many IPv6-only plans ship it and only need
   the resolver set — ask support for the DNS64 address, then put it in
   `/etc/systemd/resolved.conf` (`DNS=…`) and `systemctl restart systemd-resolved`.
4. **A public NAT64 resolver**, e.g. `2a01:4f9:c010:3f02::1` (nat64.net). Free and it works, but a
   stranger's box then sees which hosts you connect to. TLS keeps the token and the messages
   themselves private; treat this as a stopgap, not a setup.

Everything else the deploy needs — PyPI, OpenRouter, the Debian/Ubuntu mirrors — is reachable over
IPv6 already. GitHub is not, so with options 2 and 4 the code goes to the server by `rsync`
instead of `git clone` (last section).

## The Telegram relay on Cloudflare Workers

`deploy/worker/` is a ~40-line Worker that forwards `/bot<token>/<method>` and
`/file/bot<token>/<path>` to `api.telegram.org` unchanged. Cloudflare is dual-stack, so the bot
reaches the Worker over IPv6 and the Worker reaches Telegram over IPv4. aiogram treats it as an
ordinary Bot API server, so long polling, sending and callbacks all work as before.

```bash
cd deploy/worker
npx wrangler login
npx wrangler deploy                          # creates the Worker; secrets need it to exist
npx wrangler secret put TELEGRAM_BOT_TOKEN   # the same token the bot uses
```

Between those two commands the Worker is up without its secret, which means `env.TELEGRAM_BOT_TOKEN`
is `undefined`, no path can match it, and every request gets a `404`. The window is safe, not open.

**Give it a minute before believing a failure.** A deploy or a new secret reaches Cloudflare's edge
over roughly half a minute, and not to every location at once — during that window the same request
alternates between the old code and the new. A `404` right after `wrangler secret put` usually
means the edge has not caught up, not that anything is wrong. Retry before debugging.

To avoid a copy-paste mismatch, feed the secret straight from the file rather than the clipboard:

```bash
grep '^TELEGRAM_BOT_TOKEN=' ../../.env | cut -d= -f2- | npx wrangler secret put TELEGRAM_BOT_TOKEN
```

`wrangler deploy` prints the URL. Put its origin — scheme and host, no path — into the server
environment:

```
TELEGRAM_API_ORIGIN=https://timeknot-telegram-relay.<subdomain>.workers.dev
```

Leave it unset and the bot calls `api.telegram.org` directly, which is what you want anywhere with
IPv4.

Two things worth knowing:

- **The relay is pinned to one token.** It compares the token in the path against the secret and
  answers `404` to anything else, so it cannot be used as an open relay by whoever finds the URL.
- **Do not turn on request logging for this Worker.** The bot token is part of every request path.
  `wrangler.toml` deliberately has no observability block.

Cost is nil in practice: long polling holds one request open at a time, roughly 3k requests a day
against a free-plan allowance of 100k.

Check the relay end to end before pointing the bot at it:

```bash
TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2-)
curl -s "https://<your-worker>.workers.dev/bot$TOKEN/getMe"
```

`{"ok":true,…}` means the whole path works: your host reached Cloudflare, Cloudflare reached
Telegram, and the token matched the secret.

## First deploy

Sized for the smallest VPS: 1 core, 2 GB RAM, 15 GB disk is far more than this needs.

**1. System packages and the service user.** As root:

```bash
apt update && apt install -y git curl ca-certificates
adduser --system --group --no-create-home --home /nonexistent timeknot
```

**2. `uv`.** The standalone installer pulls the binary from GitHub releases, so it needs the IPv4
egress from above to be working:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
ln -sf /root/.local/bin/uv /usr/local/bin/uv
```

**3. The code**, root-owned and read-only to the service:

```bash
git clone https://github.com/nikitabaskov/TimeKnot.git /opt/timeknot
cd /opt/timeknot
uv sync --frozen --no-dev
```

`uv sync` builds `/opt/timeknot/.venv` and installs the project, which is what puts the
`timeknot` entry point on disk at `/opt/timeknot/.venv/bin/timeknot`.

**4. The environment file.** Secrets live only here, mode `0600`, outside the repository:

```bash
install -d -m 0755 /etc/timeknot
install -m 0600 /opt/timeknot/deploy/timeknot.env.example /etc/timeknot/timeknot.env
editor /etc/timeknot/timeknot.env
```

Fill in `TELEGRAM_BOT_TOKEN`, `OWNER_USER_IDS`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and set
`TIMEZONE` if you are not in Krasnoyarsk. Leave `DATABASE_PATH` pointing at
`/var/lib/timeknot/timeknot.db`.

**5. The unit:**

```bash
install -m 0644 /opt/timeknot/deploy/timeknot.service /etc/systemd/system/timeknot.service
systemctl daemon-reload
systemctl enable --now timeknot
systemctl status timeknot
```

`/var/lib/timeknot` is created by systemd itself (`StateDirectory=`), owned by the service user,
mode `0700`. The database is the only state; back that one file up and you have backed up
everything.

## Updating a running instance

```bash
cd /opt/timeknot
git pull
uv sync --frozen --no-dev
systemctl restart timeknot
```

The database is untouched — it lives in `/var/lib/timeknot`, not here. Schema changes are applied
on startup by `create_schema`. Reminders scheduled before the restart are re-armed from the
database during rehydration, and anything that came due while the process was down is sent
immediately, marked as late.

To roll back, `git checkout <sha>` and repeat the last two commands.

## Logs

Everything goes to journald under the `timeknot` identifier:

```bash
journalctl -u timeknot -f              # follow
journalctl -u timeknot -p warning      # provider failures, failed sends, unusable model output
journalctl -u timeknot --since '1 hour ago'
```

Worth recognising:

- `The provider could not be reached` — OpenRouter is down, rate limiting, or the key is wrong.
  The exception text carries the status code. The owner saw a "модель недоступна" reply.
- `The model returned unusable output twice` — the retry did not help; the pydantic complaint is
  in the traceback.
- `Failed to send reminder for task N` — Telegram refused the send. The task stays unmarked and
  goes out again on the next dispatch, so this never loses a reminder.

## Verifying by hand after a deploy

1. Write the bot anything — it answers.
2. `напомни через 2 минуты проверить деплой` — the confirmation shows the local time.
3. `reboot` the machine before that reminder is due.
4. After the box comes back, `systemctl status timeknot` is `active (running)` without anyone
   logging in, and the reminder still arrives with its two buttons.
5. Press «Отложить на 1 час», then `/tasks` — the new time is there.

Step 3 is the one that matters: it proves both the enable-on-boot and the rehydration path at
once.

## If GitHub is unreachable and you would rather not fix that

Push the working tree straight from the development machine instead of cloning:

```bash
rsync -az --delete \
  --exclude .git --exclude .venv --exclude .scratch \
  --exclude __pycache__ --exclude '*.db' --exclude .env \
  ./ root@[<ipv6>]:/opt/timeknot/
```

Then continue from step 4. `uv sync` still needs PyPI, which is fine over IPv6. Note that this
leaves the server without a `git pull` path, so every update goes through `rsync` too.
