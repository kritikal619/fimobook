# 2026-10-07 production recovery

Production: `fimobook-prod` / `3.38.224.136` / hostname `ip-172-26-14-37`.
The ED25519 fingerprint matched the user-provided fingerprint. The old 2 GB
instance was not used or modified.

## Evidence and cause

- Initial load was about 7 on 2 vCPUs. RAM available was about 1.9 GiB;
  the root filesystem had 64 GiB free. No kernel OOM evidence was found.
- Nginx configuration, listener ports and Unix socket permissions were valid.
  Socket and local Nginx homepage probes timed out.
- Gunicorn repeatedly logged WORKER TIMEOUT and replaced workers. The first
  timeout after the preceding recovery was 2026-10-07 05:47:40 UTC / 14:47:40 KST.
  A Gunicorn SIGKILL message suggesting OOM was not corroborated by kernel logs.
- CPU steal reached 79–81%. This confirms severe CPU scheduling pressure;
  Lightsail burst-credit depletion is plausible but was not verified through
  AWS account metrics (AWS CLI was unavailable locally).
- Evolution statistics expired every 300 seconds in each process and rebuilt
  synchronously inside the homepage request. Market statistics recomputed on
  every homepage request. Review metadata repeatedly searched all 16,870 players
  and processed all reviews/summaries to display three homepage items.
- Live py-spy stack reads showed all synchronous workers occupied by Nexon live
  price fetches, Firestore fallback queries or player filters. A lock around live
  price network requests could also hold other request threads waiting.
- The renewal timer runs every 15 seconds. Its job repeatedly imported the full
  app and loaded/decoded the 50 MB player catalog even though it only needs models
  and the renewal card file. Runs consumed about 22–25 CPU seconds and ran almost
  continuously. Coupon notifications loaded the same unused catalog.
- The 15:00 KST price snapshot ran from 06:00 to 06:23 UTC and consumed 22.389 CPU
  seconds total. The first timeout preceded it. The player-refresh job was idle.

## Exact deployed files

1. `/home/ubuntu/fimobook/app.py`: shared asynchronous statistics; CID index;
   limit homepage metadata to displayed items; nonblocking price-cache contention;
   optionally skip the player catalog only in notification processes.
2. `/home/ubuntu/fimobook/derived_cache.py`: disposable shared JSON caches with
   source-file signatures, nonblocking cross-process flock, background builds,
   atomic publication, reuse of unchanged decoded cache files and saved results.
3. `/home/ubuntu/fimobook/jobs/renewal_push_job.py`: opt out of unused player load.
4. `/home/ubuntu/fimobook/jobs/coupon_webpush_job.py`: same notification-only opt-out.
5. `/etc/systemd/system/fimobook.service.d/zz-request-timeout.conf`: persistent
   `--workers 2 --threads 4 --timeout 180`; all other service arguments unchanged.
   Repository copy: `ops/systemd/fimobook.service.d/zz-request-timeout.conf`.

Input databases, secrets, uploads, DNS, firewall and timer unit configurations
were not replaced or deleted. No Git staging, push or broad project sync occurred.
The production app had unrelated differences from the Mac checkout; deployment
used the actual server source and preserved those differences and file modes.

## Recovery and validation

Read systemd/journal, Nginx configuration/logs, processes, resources and listeners.
Temporarily stopped Nginx and coupon/renewal timers during recovery, then restored
them. Staged only the affected files under `/tmp/fimobook-recovery-20261007`,
kept original source backups there, installed with preserved ownership/modes,
used `systemctl daemon-reload`, service restart and Gunicorn HUP for changes.
The profiler was installed only under the same `/tmp` recovery directory.

The final service was restarted at 2026-10-07 06:42:52 UTC / 15:42:52 KST with
timers active. Saved statistics timestamps remained 06:30:51 and 06:30:57 UTC,
showing cache reuse across service restarts and beyond the former five-minute TTL.
The statistics API returned `source=snapshot`, `error=false`, the 15:00 KST
snapshot and 107 history points. Full Fimobook HTML was checked for public and
origin responses, rather than accepting status alone.

After removing unused catalog loading, renewal job CPU usage was 1.685 seconds
instead of roughly 24 seconds. A subsequent vmstat sample showed 99–100% idle
and 0% steal. Observed responses before final restart: socket 0.067 seconds,
local Nginx 0.077 seconds, direct origin 0.132 seconds, Cloudflare 0.952 seconds;
all HTTP 200. Final verification is recorded in the task response.

Focused checks exercised nonblocking cold cache fallback, one in-process builder,
saved cache reuse, source-change refresh, newest-three review hydration and price
lock contention/release. No broad test suite or notification job was manually run.
Normal timer runs were inspected for successful completion.

## Operational limits

These are persistent code/service changes, not a one-time warmup. Cache files in
`instance/derived_statistics` are derived/disposable; a cold cache serves local or
saved data while one background builder refreshes it. Background build failures
keep the previous value and log errors. External Firestore index errors remain a
separate pre-existing issue; no Firebase account settings were changed.

CPU/burst capacity should still be checked in Lightsail if latency or steal
recurs. External API latency and future traffic can still exhaust finite request
capacity; the recovery does not guarantee unlimited traffic or eliminate all
upstream dependencies. Timer schedules remain unchanged.

## Final observed state

At 06:44:38 UTC / 15:44:38 KST, service, Nginx and all four original timers
were active. The socket backlog was zero. Final workers were 130462/130463
under master 130458, unchanged since the final restart. No WORKER TIMEOUT,
traceback or request-handling exception was logged after that restart, and no
new Nginx upstream error was found from 06:43 UTC onward at this check.
Renewal runs completed in 1.6–2.4 CPU seconds; coupon run used 1.724 seconds.
Load fell from about 7 to 0.44 and available RAM rose to 2.6 GiB.
Cloudflare and direct origin both returned full Fimobook HTML with HTTP 200
in 0.110 and 0.120 seconds respectively. Repeated internal homepage checks
were roughly 0.06–0.12 seconds and statistics checks 0.003–0.004 seconds.

Additional page checks: player detail HTTP 200 in 0.646 seconds; search HTTP 200
in 0.201 seconds with a complete normal browser User-Agent. Plain curl and bare
`Mozilla/5.0` returned 403 under an existing Nginx automation-blocking map; this
rule was inspected and preserved. The final restart caused a brief expected
socket gap, with the last corresponding Nginx entry at 06:42:53 UTC; subsequent
upstream error checks start at 06:43 UTC.
