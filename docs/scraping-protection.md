# Public data collection restrictions

## Scope

`scraping_protection.py` rejects direct downloads of renewal/player raw files
and requires a signed page token plus its matching session cookie for:

- `/autocomplete`
- `/api/squad_players`
- `/api/player_compare`
- `/api/player_details_by_name`
- `/api/player_prices`
- `/api/player_price/<cid>`

The existing Flask-WTF token is attached by `page-data-access.js`, loaded before
page scripts in both base templates and the standalone squad/compare templates.
Read tokens use the Flask session lifetime. Write CSRF validation is unchanged.
Protected JSON and HTML containing tokens must not be shared-cached. Existing
CDN JSON entries may require expiration or an authorized cache purge at rollout.

Both local Nginx configuration sets include the same protection. Static raw
files must be denied at Nginx too because Nginx serves `/static/` without Flask.
The existing trusted Cloudflare address configuration restores visitor IPs;
do not trust arbitrary forwarded IP headers in Flask.

Nginx budgets:

- Existing search results: 5 requests/minute with burst 15.
- Existing autocomplete: 2 requests/second with burst 20.
- Protected player APIs: shared 30 requests/minute with burst 40.
- `/times`: 6 requests/minute with burst 12.

These are sustained leaky-bucket rates, not fixed calendar-minute quotas.
Common command-line automation user agents are rejected on these Nginx routes.
Thresholds may need adjustment for users behind shared IPs. Do not add a
user-agent-only Googlebot bypass: that would let scrapers impersonate Google.

## SEO and limitations

`/times`, `/player/<cid>`, the homepage, sitemaps, indexing directives, and
server-rendered content are preserved. The API routes were already noindex.
No login or JavaScript challenge is added to indexable pages. Production SEO
and normal mobile/TWA behavior still need runtime observation after rollout.

This raises collection cost, but does not establish that a requester is human.
Bots can acquire page tokens and cookies, change user agents, read public HTML
slowly, or rotate IPs. Renewal data also originates from a publicly available
upstream; restrictions on this site cannot prevent another site's collection
or use of previously copied data. The command example alone does not identify
the bot's source or implementation.

No test suite was run or added. Production deployment completed on 2026-10-04
(Asia/Seoul) after Python/JS/Jinja syntax and server dependency checks. Changes
were applied to copies of the current production files, preserving unrelated
code, configuration, ownership and modes. Nine deployed files: `app.py`,
`scraping_protection.py`, `static/js/page-data-access.js`, four templates
(`base.html`, `v2/base.html`, `squad_maker.html`, `compare_interactive.html`),
and the active Nginx zone/site files. Nginx configuration validation passed,
the app restarted, Nginx reloaded, and both services were active.

Public deployment checks confirmed:

- Homepage, renewal HTML, player detail and sitemap: HTTP 200.
- Session-authorized autocomplete, player search and comparison: HTTP 200.
- Missing token or copied token without its matching session: HTTP 403.
- Raw renewal/player JSON URLs: HTTP 404, including the canonical renewal URL
  through Cloudflare without a cache-busting query.
- Recognizable script client on `/times`: HTTP 403.
- Googlebot user-agent on `/times`: HTTP 200. This checks route accessibility,
  not verified crawler identity or actual search ranking.
- Actual browser autocomplete displayed player suggestions; live price updates
  also rendered. No new application exception markers were found after restart.
- All nine installed file hashes matched the staged candidates.

Backups remain at `/tmp/fimobook-scraping-deploy.dNTkk3/backups` on production.
No external account settings, secrets, databases or player data were changed.

## Follow-up at 20:34 KST

Access logs showed successful `/times` reads at 20:34:28 and 20:34:46 from
the legacy `Android 2.0; en-us; Droid Build/ESD20` client identity. This client
also read the HTML repeatedly before and just after deployment. Logs establish
successful HTML access, but do not prove it was the specific messenger bot.

At approximately 20:39 KST, the Nginx automation map was extended to reject
this distinctive legacy identity on protected routes. Flask also rejects its
exact user-agent on `/times`, search/data endpoints, player detail variants,
and stats-card output. No visitor IP was blocked. The initial Nginx validation
reported a map hash bucket size error for the long literal; the rule was changed
to a regex before reload. Validation then passed and both services were active.

Public checks: the observed identity received HTTP 403 on renewal and player
detail, while a normal mobile client and Googlebot user-agent received HTTP 200
on the relevant pages; sitemap remained HTTP 200. App workers started without
new exception markers. Backups are retained in
`/tmp/fimobook-legacy-client-block.j9ddum/backups`.

This is a targeted incident restriction. Changing user-agent, obtaining page
tokens, reading public HTML, or using copied/upstream data can still bypass the
overall collection deterrence. No verified-human challenge is configured.

## Follow-up at 20:43 KST

Origin logs show `/times` returning HTTP 200 at 20:43:02, 20:43:16 and
20:43:17 to the same source IP, using a full Windows Chrome 128 user-agent
and a homepage referrer. This matches the user's reported timing, though logs
alone cannot attribute the requests to the messenger bot's operator. The
current gates do not prevent reading the indexable HTML with this identity.
No additional user-agent or source-IP ban was applied for this report.

The existing public login page already loads a reCAPTCHA widget. A stronger
human-verification gate would change the normal visitor experience and requires
verified crawler access to preserve crawlability. The user was asked whether
to add that interaction. No human-verification gate has been enabled while
awaiting that decision, and zero SEO impact has not been promised.

The user subsequently confirmed the 20:43:02/16/17 client as the unwanted
collector and explicitly requested blocking it and its device. The unique
source IP was `14.53.39.133`. At approximately 20:47 KST, an exact-IP `return
403` rule was installed in both production HTTP/HTTPS server blocks, before
location routing. This also covers locations with their own access directives.
Only the active Nginx site file changed; its ownership/mode were preserved.
Nginx validation/reload passed, both services remained active, and public
`/times` and `/sitemap.xml` checks returned HTTP 200 for another visitor.

Backup: `/tmp/fimobook-confirmed-client-block-wkg_tx0t/fimobook.before.conf`.
At the final log inspection, the client had not made a new request after the
rule was applied, so no post-change response to that actual client had yet been
observed. Source-IP blocking does not identify physical devices: another IP,
VPN, or another network can evade it, and other visitors sharing this IP are
subject to the same rule. No global Chrome 128 or mobile-device ban was added.
The human-verification proposal was not enabled.
