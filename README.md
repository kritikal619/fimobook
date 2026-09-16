# fimobook

## Production security settings

Set these values in the server environment rather than committing them:

```sh
FIMOBOOK_SECRET_KEY=<long-random-secret>
FIMOBOOK_ADMIN_EMAILS=<verified-admin-email>
FIMOBOOK_ADMIN_SETUP_PASSWORD=<long-random-password>
FIMOBOOK_ADMIN_USER_DELETE_PASSWORD=<long-random-password>
PLAYER_SUMMARY_ADMIN_PASSWORD=<long-random-password>
```

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
