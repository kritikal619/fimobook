# fimobook

## Production security settings

Set these values in the server environment rather than committing them:

```sh
FIMOBOOK_SECRET_KEY=<long-random-secret>
FIMOBOOK_ADMIN_EMAILS=<verified-admin-email>
FIMOBOOK_ADMIN_SETUP_EMAIL=<verified-initial-admin-email>
FIMOBOOK_ADMIN_SETUP_PASSWORD=<long-random-password>
FIMOBOOK_ADMIN_USER_DELETE_PASSWORD=<long-random-password>
PLAYER_SUMMARY_ADMIN_PASSWORD=<long-random-password>
```

The setup password is accepted once, only when no administrator exists, and
only by the verified FIMOBOOK_ADMIN_SETUP_EMAIL account. Configure additional
trusted administrators through FIMOBOOK_ADMIN_EMAILS or
FIMOBOOK_ADMIN_USER_IDS. Rotate or remove the setup password after bootstrap.
FIMOBOOK_ADMIN_USERNAMES no longer grants administrator access because
usernames are self-selected; migrate those entries to verified admin emails
or review each stored is_admin grant before deployment.

If `FIMOBOOK_SECRET_KEY` is omitted, the app creates a private,
server-local key in `instance/.secret_key`. Deploying this security change
invalidates sessions that were signed with the old hard-coded key.

Generate static sitemaps:
```
python scripts/generate_sitemaps.py
```

## Firebase tier voting

Community player tiers are stored in Firestore under:

- `player_tier_votes/{player_cid}`: aggregate `counts`, `total`, and `updated_at`
- `player_tier_votes/{player_cid}/votes/{user_id}`: the authenticated user's current tier

The server writes both documents in one Firestore transaction, so changing or
canceling a vote updates the aggregate without creating a duplicate vote.

## Twice-daily player price history

Prices are stored separately from `instance/board.db` in
`instance/player_price_history.db`. Each player/scheduled-time row contains the
complete 0-15 enhancement price array, so a rerun of the same 03:00 or 15:00
KST slot replaces that snapshot without creating duplicates.

Run a live collection manually:

```sh
venv/bin/python jobs/player_price_snapshot_job.py
```

Validate the storage path without calling Nexon by loading the current data
file (the normal safety thresholds still apply):

```sh
venv/bin/python jobs/player_price_snapshot_job.py --from-file player_data.json
```

Production systemd templates are in `ops/systemd/`. The timer runs twice daily
at 03:00 and 15:00 Asia/Seoul, retries a missed run after a reboot
(`Persistent=true`), and retries a failed upstream collection up to two more
times at 30-minute intervals. It refuses to overwrite a good snapshot when the crawl returns
suspiciously few players. Override the database or safety thresholds with
`FIMOBOOK_PRICE_HISTORY_DB`, `FIMOBOOK_PRICE_MIN_FETCHED`, and
`FIMOBOOK_PRICE_MIN_PRICED` when necessary.
