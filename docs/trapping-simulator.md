# 트래핑의 신 시뮬레이터

Route: `/trapping-simulator`, linked from the pack opener. The game is client-side (`templates/trapping_simulator.html`, `static/js/trapping-simulator.js`, `static/css/trapping-simulator.css`). The three fixed mode photos use the original supplied screenshot crops (`chest.webp`, `head.webp`, `foot.webp`); rules and rewards also use the October 15 recording. The large event header, progress gauge, adjacent reward explanations, FV controls and custom disclaimer have been removed at the user's request.

## Playing and resources

Chest: +3P at 30% / super 50%. Head: +2P at 50% / super 65%. Foot: +1P at 70% / super 80%. Super applies only when the points before an attempt equal 3, 6, 9, 12, 15, 18 or 21P. Gains cap at 24P. Outcomes use rejection-sampled `crypto.getRandomValues` and are saved before animation, so refresh cannot reroll an attempt.

The current points, highest points and reward-row highlight update immediately when the result is saved, before any success effect finishes. The fixed photos do not switch or move, and no video element or recording-derived media is loaded. Success uses a brief point popup, small confetti and border glow. Fast mode and reduced-motion preferences skip that effect. Super points retain the fixed photos and the pre-existing super labels/flames and probabilities; the user's briefly requested blue restyling was cancelled. Storage changes cancel obsolete effects.

The rank button lets the user explicitly select Amateur (100 tickets), Semi-pro (80) or Pro (70). An explicit selection is independent of highest reached points, persists, and sets future entry costs. Existing rounds retain their original cost. Before the first manual selection, the original highest-point ranking still applies.

`추가하기` directly grants the entered number of tickets (1–1,000,000 per action, up to a 1,000,000,000 balance), with 100/1,000/10,000 presets. There are no FV purchases or exchange-token controls. Initial tickets remain 1,000.

## Mail and reward screens

Stopping at a successful point sends its reward pack plus the corresponding point-ticket return as one mail. A failed attempt automatically ends the round and sends only the participation pack, with tickets equal to the points attained. There is no failure reward-choice dialog or failed-round point-reward recovery. A saved failed round is also settled on loading when no receipt is active. Only the awarded mail is queued; tickets are credited on receipt. Reaching 24P still opens the final-reward dialog. Attendance rewards at 5/10/25/40/60/100/200 entries are each sent once.

The header mailbox supports individual and all-mail receipt. A receipt removes the selected mail, credits attached tickets, records received mail, and persists the same reveal in one saved object. Web Locks serialize receipt/acknowledgement where available. Pending mail is never truncated. Completed received-mail history retains 200 entries and completed-round history retains 100.

Receipt replaces the entire game view, including its records panel, with the pack opener's actual background, scaled 1024×576 screen, summary layout, item presentation and Next button. Both templates include `templates/_pack_reward_flow.html` and use `static/css/pack-opener.css`. Pack opener behavior is unchanged; its existing JavaScript continues to control the same DOM IDs. The trap page controls its own instance and never loads the pack opener's shop/draw script. On mobile the Next/fullscreen touch targets remain usable while preserving the scene.

Refresh during receipt restores the already credited reveal. Next acknowledges it and returns to the game without another grant. Mail can be received during an active round; returning preserves that round. On receipt each mail is opened against the official 트래핑의 신 odds (`WEBG_TRAPPING` category of https://fcmobile.nexon.com/ForumProbability, saved in `static/data/trapping_probabilities.json`: 24 point-reward packs, the participation pack and the 5/10/25/40/60/100/200 attendance packs). `POST /api/trapping-simulator/draw` (allow-listed pack IDs only) reuses `PackCatalog.draw` from the pack opener and returns players/MP; the result is saved in `state.delivery.result` so a refresh never redraws. The reveal reuses the pack opener's step flow (pack click → next reward, 모두 열기 → summary with player cards and current value). Mail whose pack has no official table is still shown as the awarded pack. Refresh the data with `scripts/sync_pack_probabilities.py`'s client (`ProbabilityClient`) against `WEBG_TRAPPING`; the default `pack_probabilities.json` sync does not include it.

## Storage migration

The localStorage key remains `fimobook.trapping.v1`, with payload `version:2`. Version-1 inventory packs migrate into pending mail with deterministic IDs. Their `tickets` attachment is zero because version 1 already credited those tickets. Existing balances, rounds, statistics, attendance claims and history are retained. Removed FV/exchange bookkeeping is discarded. A manual rank override, mailbox, received log and in-progress delivery are persisted. Reset only affects this simulator.

## Source limits and inspection

Reward names through 22P and attendance rewards are transcribed from the supplied screenshots. The recording resolves the last two tiers: 23P is `[10-12진화][GC27 포함] 선수 144-148 또는 90억 MP`, and 24P is `[3-5진화][TOP20] 선수 145-148`. Failure FV purchases and attained-point recovery are not offered, as requested. There is no substitution of unrelated shop-pack odds or arbitrary player draws.

The current runtime uses the original static mode crops, badge, ticket, super banner and shared pack-opener receipt assets. Recording MP4s and cleaned derivative stills remain on disk as earlier work but are not referenced by this simulator. Their historical prompts and provenance remain in `docs/trapping-simulator-assets.md`.

Dark mode follows the existing `data-theme` switch. The event surface, wallet, reward rows, current-row highlight, records and native dialogs now have paired dark backgrounds/foregrounds, including mailbox, rank selection and ticket inputs. The site's existing theme controls and stored preference are reused.

No test suite was run or added. JavaScript syntax was checked. Manual DOM/visual inspection confirmed the three original photo URLs, zero video elements, dark event/table surfaces and dark mailbox text/background. Existing gameplay data was not cleared or spent for this inspection. Earlier interactions and revisions are retained in `design-qa.md`; current evidence is `artifacts/trapping-simulator/static-dark-*`.
