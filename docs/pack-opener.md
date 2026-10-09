# FC모바일 팩 오프너

Local route: `/pack-opener`. Linked from the shared menu and home shortcuts. This is a free simulator; it has no game account, currency, purchase or reward transfer integration.

## Probability source

`static/data/pack_probabilities.json` contains the complete Nexon ForumProbability STORE snapshot captured on 2026-10-03 KST: 17 products, every nested table, and every 100-row detail page. Names, quantities, base OVR, evolution levels and displayed percentage strings are preserved.

Refresh deliberately with `python scripts/sync_pack_probabilities.py` from the repository root. The command visits the public page for its anti-forgery cookie, reads only the public probability APIs and replaces the snapshot only after every pack is fetched. It does not require login or credentials. The UI shows the snapshot date and links to the official source. There is no automatic refresh or implied live synchronization.

`pack_opener.py` chooses outcomes with integer weights at the actual decimal precision of each table using `secrets.randbelow`. Published rounding discrepancies around a total of 100 are handled by drawing from the sum of the published weights. A discrepancy over 0.01 percentage points is rejected. Every 100% row is guaranteed; other positive rows form a separate weighted choice. Nested quantities cause independent repeated draws, including the 10-pack sets. Leaf quantities are preserved (e.g. 75 evolution tokens plus a player/MP outcome). Returned probabilities multiply the selected path's original percentages, with no resampling when a player cannot be resolved.

## Player and media mapping

The snapshot has 1,886 distinct name/base-OVR combinations. All were resolved against the current player_data.json during authoring. Matching also uses official face/background program identifiers: className alone mislabels a number of HERO cards. TWG variants and UCL BESTXI variants are matched explicitly. Identical visual duplicates use the smallest CID; the source does not specify trade status, so the UI does not infer it. A future unresolved row retains its official name, OVR, evolution and probability with a placeholder, never an unrelated player.

Card and face layers reuse the existing local `static/card` and `static/faceon` assets with original source URLs as fallback. The official card text colors are saved in `static/data/pack_card_colors.json`. 271 official country flags/club badges are saved under `static/pack-opener/flags` and `clubs`. Official SquadMaker league logos are saved under `static/pack-opener/leagues`; missing official assets are omitted rather than replaced with another league. Card geometry and badge rules were inspected from the public SquadMaker app (`app.2o14Vja0.js` and `app.css`) on 2026-10-03.

`static/pack-opener/images` contains the supplied background and transparent pack image. `static/pack-opener/videos` contains 52 web-compatible H.264 videos from the previously converted Sappurit/s10img PACKOPENING_1024x768 folder. The SSD copies are unchanged. Unknown/unavailable season animations use DEFAULT26 and the UI discloses that fallback. FCA27 does not reuse FCA26's anniversary movie. The season map is explicit in `ANIMATIONS`; TOTS/UTOTS share the TOTS program animation, while UCL uses the default. Korean CL26 uses CAP26 (Capped Legends), as clarified by the user; the supplied packopening_CL26 movies feature CONMEBOL Libertadores. Players whose original background program is LNY26 use the LNY26 animation even when their generic class name is HERO & UH24 (including CID 22901386, H. Kewell).

## Animation and state

Cards preserve the official SquadMaker’s square artwork without cropping either side. Face layers use 95% of the canvas; OVR/position, name and country/league/team badges use the official relative positions. League badges follow the official program exclusions, and offset star-card layouts retain their special name/badge positions. Season artwork remains the resolved player’s original background. The featured card occupies 19% of the stage width. Evolution uses the squad-maker badges at its existing coordinates; MP uses a transparent cutout of `static/images/ea-token.png` saved as `static/pack-opener/images/mp-token-transparent.png`.

The stage plays pack shockwave → matching season movie 1 → flag/position/club overlays timed against movie currentTime → movie 2 → glowing card silhouette → full reward summary. Movie 2 loops behind the revealed card until Next is pressed; Next, Skip and cancellation stop playback. For multi-reward packs, the highest base-OVR player gets the featured animation and all drawn rewards are included in the summary. Media failures show the already drawn results without redrawing. Replay does not draw or save another outcome. Skip cancels the current playback and displays the same outcome. Reduced motion retains the requested movie with soft glows, small sparkles and card fades. Optional sounds are synthesized, not original game audio.

The latest 100 individual rewards and the number of opened products are saved locally in the browser; 20 appear in the recent strip. A set counts as one opened product. History is not saved to user accounts or the server.

After the featured card/scoreboard, Next opens the complete reward overview immediately. Skipping the opening or opening an item-only pack enters the supplied second recording's individual reward flow on the same stage: a pack on the left shows the remaining count, individual rewards sit to the right of the left-hand pack, pressing the pack or current reward reveals the next item, and Open All shows the entire drawn bundle. A reward already shown as the featured card is not repeated in the individual queue, but remains in the complete overview. The overview's Next returns to the pack, and Replay uses the same draw. Item-only packs follow the same flow. Detailed quantities, probabilities and player links remain available in the expandable result details. MP amounts from the same opening are combined into one reward in the reveal queue, overview, details and newly saved history. Original draws remain unchanged; an expandable MP breakdown retains each amount and its actual probability without inventing an aggregate probability. MP from different openings is not combined. No extra currencies from the recording are invented; only official outcomes are displayed.

## Authoring review

Manual desktop/mobile visual review was performed in the local preview. No automated tests or test suite were run, per repository instructions. No production deployment or GitHub push is included.

## Reward value labels

The featured player, individual player rewards and complete overview show the recording's “현재 가치” label, transparent MP coin and numeric MP price. Prices use the drawn evolution level's exact `n8Price{level}` field, then refresh through the existing `/api/player_prices` service without delaying the animation. A stale request cannot change another opening. Missing exact-level prices show “가격 정보 없음”; no base/other-level substitution is made. Hover text identifies stored vs recently queried prices. Season/name/evolution metadata remains in card artwork, result details and history.

## Shop FV prices

`static/data/pack_shop_prices.json` maps 13 exact product IDs to the FV prices in the user-supplied shop screenshots on 2026-10-03. It is separate from the probability snapshot, so probability refreshes cannot overwrite screenshot prices. Unpictured prices remain null and show “가격 미확인”; no cost or currency deduction is invented. Prices appear in the product list and selected product information with `static/pack-opener/images/fv-token-transparent.png`, a built-in imagegen background extraction preserving the green hexagon, white mark and black interior while removing the outer rectangle. Individual MP icons are 14% of stage width; current-value labels, amounts and MP coins are enlarged, with smaller overview styles for bundles.

## Shared card artwork and item-only rewards (2026-10-03)

`player_card_art.py` supplies original program colors and country/league/club badge visibility before local image normalization. `player-card-art.js` and its stylesheet share the square canvas, fonts and positions across detail, search results, squad, comparisons and review cards. Existing growth calculations remain with their original page controllers. Missing player artwork continues to use the existing placeholder.

MP rewards are combined within each opening and placed first in the individual flow, overview, detail list and newly saved history. The highest player can still headline the cinematic. The user-supplied metallic jersey coin is preserved as `mp-reward-source.png`; built-in imagegen removed its outer teal background into `mp-reward-transparent.png`. Price-caption coins retain their smaller original asset.

A single currency/item reward hides the empty remaining-pack control and uses a centered stage-relative icon and readable amount. Multiple rewards retain the pack/reward layout and the overview uses consistent item sizing. Guaranteed 75/150 NG token wrappers are counted directly rather than rejected by the random-bundle size guard; randomized oversized bundles remain guarded. This update was reviewed manually in the local UI; no automated tests were run.

Mixed reward overviews size the MP coin to 65% of its card slot rather than a fixed stage-width size. Its top inset and MP/amount captions use the same slot proportions, matching the user’s mixed-results screenshot while keeping the larger item-only layout.

Cinematic nation/club hints are enlarged and the artificial white drop-shadow halo is removed. Stage background clicks open/skip/advance according to the current phase; controls do not double advance and the final overview requires its Next button (Escape does not dismiss it). All devices use one 1024×576 desktop canvas, uniformly scaled inside the embedded/fullscreen wrapper with black letterboxing as needed. Scene-specific responsive rules follow the canvas container rather than viewport breakpoints, preserving composition, reward columns, fonts and button proportions across mobile and desktop.

Dark program lettering (OVR, position and name) now has no text shadow, filter or stroke, through the shared card renderer on all integrated pages. Light lettering retains its contrast shadow.

The shop omits the manager rename card and Treasure Hunter ticket exchange. User-confirmed KL26 pack prices are 500/900 FV. Skip opens the complete overview directly; no zero-count remaining pack is shown. Recent player rewards show exact-level MP prices. The homepage promo rail defaults to its new first slide, 팩깡 시뮬레이터. Decorative pack header text was removed.

The featured cinematic no longer shows a price. Its Next control matches the supplied 14:23:35 recording at 17 seconds: a centered “다음” in a translucent dark full-width strip near the bottom, without an arrow or cyan filled button. Individual rewards, overview and history retain their prices.

## Quantities and cumulative acquisition totals

The quantity input accepts 1–100 product units (a set is one product unit), previews the total FV, and submits one draw request. The server validates the integer quantity and performs independent official draws for each unit, returning one combined result and the confirmed FV cost. MP is combined for the batch, while players remain individual rewards; replay never draws again.

Browser history stores cumulative FV, raw MP, and exact-evolution player values at acquisition, independently of the capped recent-card list. Unknown prices are explicitly excluded rather than guessed. Pre-existing history lacked FV costs, so monetary totals start with new openings; the old cards remain visible. Reset saves a separate browser backup, and Undo restores it while retaining any openings since reset. Quantity/reset/undo are disabled during an opening. No automated tests were run.


Mobile pack selection uses a native modal with full-width searchable pack rows, readable FV pricing and a close control; the same shop DOM moves back into the desktop sidebar when its breakpoint changes. Quantity/history controls retain touch-sized targets outside the scene. The explanatory prose lives in a collapsed 이용안내 disclosure, and the redundant history/new-opening and selection descriptions were removed.

Deployed on 2026-10-03 to fimobook-prod with a 399-file allowlist: the new pack modules, probability/color/price snapshots, 52 animation MP4s, pack/badge assets, shared card renderer, affected legacy templates and squad renderer. Production app edits were transplanted into its existing source, preserving its separate V2 implementation and unrelated local changes. Existing owner/mode values were preserved; changed runtime files were backed up under `/tmp/fimobook-pack-20261003-mobile/backup`. The service is active, public pack/catalog/home/squad responses were inspected, and a public two-unit draw showed FV and MP/player totals. No automated tests were run.


NG evolution material tokens now use the same square slot, icon bounds and label/amount alignment as MP in mixed reward overviews; item-only token icons use the same 14cqw sizing as MP. The latest opening displays a neutral question-mark placeholder in history until the complete reward overview is shown. The original acquisition price snapshot is retained separately while live quotes load; history is committed once on overview reveal, so replay does not add another opening. Deployed only pack-opener JS/CSS/template (cache version 20261003-26), with backups under `/tmp/fimobook-pack-token-history-20261003`.


The complete reward overview now releases the opening lock after outcomes have been recorded. Desktop shop buttons and the mobile pack-selection modal can choose another product directly from this screen, while blank clicks on the final stage still do not dismiss it. Selecting a pack cancels prior animation work and resets the scene without losing the recorded rewards. Deployed only pack-opener JS/template with cache version 20261003-27; backups in `/tmp/fimobook-pack-selection-20261003/before`.


Long reward overviews remain a continuous scroll list, with a larger 14%–88% stage-height viewport. The grid starts at the first row instead of unsafe vertical centering, resets scroll position on reveal, and exposes a scrollbar and keyboard focus; all original rewards remain rendered. MP price captions never wrap and use stage-relative compact sizing so coin and amount stay on one line. Recent acquisition totals show a user-defined multiplier: FV is converted at 3,000 FV = 20,000 KRW, and the displayed scale is anchored to 30,000 KRW + 1.5 billion MP = 50만배. This is explicitly documented as a display convention in the collapsed guide. Zero/unknown FV has no multiplier. Deployed JS/CSS/template at cache version 20261003-29; backups in `/tmp/fimobook-pack-scroll-ratio-20261003/before`. Local UI review confirmed all 100 cards, top and bottom scroll access, single-line prices and no pagination. No automated tests were run.


Display rewards now keep combined MP and other items first, then players by displayed OVR descending. Equal-OVR players are grouped by normalized Korean name, with season/CID as deterministic tie breakers. The first player in that order headlines the cinematic. The same order feeds individual rewards, overview, detailed results and newly recorded batch history; raw draw probabilities and cumulative values are unchanged. Removed the scroll instruction from the status. Local 100-card UI inspection confirmed descending OVR and contiguous same-player groups. Deployed only JS/template at cache version 20261003-30; backups in `/tmp/fimobook-pack-sort-20261003/before`.

On 2026-10-04 the user clarified the multiplier: total acquired MP value (pure MP + player value) divided directly by FV spent. 100 million MP / 1,000 FV displays 10만배. The separate KRW estimate uses 7 KRW per FV (1,000 FV = 7,000 KRW); KRW does not enter the multiplier. Existing stored totals are recalculated on render. This supersedes the earlier display convention.

On 2026-10-04 price totals were aligned with displayed quotes: exact-evolution quotes resolve before opening animation and these values are recorded only when results are revealed. History quote refresh adjusts player totals by each retained reward's accounted-price delta, including unknown-price counts. Legacy totals can be reconstructed exactly when fewer than 100 rewards remain (no history truncation); aggregate value from older truncated entries is preserved.

Loading uses the upstream vp6/loading.mp4 H.264 source in a modal dialog aligned to the fixed-ratio stage, including fullscreen. Its backdrop dims the surrounding page. It loops only while catalog/draw/quote/media/odds preparation is pending, pauses and closes on completion/failure, and contains no visible loading text. The post-reward confirmation status is empty.

Loading correction: the loading video now lives inside the scaled opening-stage with an absolute overlay; no modal dialog or page backdrop is used, so the shop, FV totals, and surrounding site remain undimmed. BLD25 maps to BO25, using the verified Ballon d'Or opening pair from Sappurit/s9img/vp6/PACKOPENING_1024x768, converted to H.264 MP4.

The loading movie is now cropped to its central animated logo and dark background colors keyed out into a VP9-alpha WebM with a transparent PNG poster. The scene-only overlay dims the underlying pack scene; no video background motifs or surrounding-page dimming remain.

## 알쏭뚝딱 방망이 (2026-10-07, local)

The catalog has separate 상점 and 알쏭뚝딱 방망이 sections and section filters. KKAEBI_BAT retains its complete official snapshot including nested tables and all detail pages; only the 17 조각달 exchange packs (01–16, 19) are exposed for opening. Purchase/use products, bonuses and guides are omitted. Existing STORE data and its original collection timestamp remain intact. Default refreshes collect both categories; --category supports scoped outputs.

Screenshot prices use 조각달, independently of FV. Pack thumbnails and 조각달/guaranteed exchange-token icons display regions of the original supplied JPGs through CSS. Reward 16 uses its actual official 140–148 table despite the 141–148 product ID. Guaranteed exchange-token outcomes are preserved as published rewards.

History separates event spending and proceeds from the STORE multiplier. User-confirmed conversion: 500 조각달 = 25,000 KRW (50 KRW/token). Event cost is the cumulative 조각달 spent multiplied by 50. The display scale follows the user's explicit example, 50,000 KRW and 500 million MP = 100,000x: event MP/player value divided by converted KRW, multiplied by 10. This convention is stated in the guide and next to event history. No tokens spent or unknown costs produce no multiplier. Player value refreshes update the appropriate event subtotal. No tests were added or run, and no production deployment or GitHub push was requested.

Deployed on 2026-10-07 with an 11-file allowlist: pack catalog module, a surgical draw-metadata change in the production app.py, pack JS/CSS/template, probability/price snapshots and four source JPGs. Production STORE tables/prices and unrelated app code were preserved; original ownership/modes were retained. Backups: /tmp/fimobook-kkaebi-20261007-1716/backup. At 390px and 375px, manual checks confirmed section switching resets a prior set filter, hides type filters for the event, restores them for STORE, supports search/selection/opening, and has no horizontal document overflow. Local MP opening recorded 225 tokens / 11,250 KRW / 100m MP / 8.89만배 with FV unchanged. Public checks confirmed 17 event packs, loaded thumbnails/tokens, official odds and a successful opening with 225-token / 11,250-KRW accounting. Service active; no recent systemd error entries. No automated test suite was run.

## Continuous opening and scoreboard playback (2026-10-07)

The previous mobile path downloaded Blob URLs and reinitialized a second movie/decoder at the scoreboard. Desktop used 2048×1536 H.264 High Level 5.0 sources (the inspected TOTY scoreboard averaged 14.4Mbps). Both paths now use one native HTTP MP4 URL and one video element throughout the opening and scoreboard. Hidden metadata/preload completion no longer gates playback; a pending or rejected autoplay request exposes a real resume button. Skip/Next/cancellation pause the same element and preserve the original result.

`scripts/build_pack_cinematics.py` builds the 25 `cinematic-v1` files from the original pairs: 1024×768, 30fps, H.264 Constrained Baseline Level 3.1, yuv420p, no audio/B-frames, 2.4Mbps VBV limit, faststart. Each movie contains a normalized 7-second intro and 12 seconds of scoreboard footage. On end, the same element seeks to the scoreboard keyframe at 7 seconds and continues; the intro and card reveal do not repeat. Video compositing is isolated on desktop as well as mobile.

Deployed with a 28-file allowlist: pack JS/CSS/template and 25 new MP4s, cache version `20261007-cinematic-1`. Production originals matched the reviewed local baseline, original ownership/modes were preserved, and all installed SHA256 hashes matched the payload. Backups: `/tmp/fimobook-cinematic-20261007-2255/backup`. The service was restarted and is active with no recent error-level journal entries. Public HTML loads one cinematic player and the new cache version; the new MP4 responds with `206 Partial Content` and `video/mp4`. Manual local desktop/390px Chrome and public Chrome checks confirmed the scoreboard playing beyond the initial opening, repeated playback, and local Next/result transition. All 25 files' encoding/duration/faststart were inspected; the TOTS seek keyframe and full decode were checked. Physical iPhone and Windows devices were unavailable; their device-specific playback remains unverified. No automated test suite was added or run.

## Reduced-motion playback follow-up (2026-10-07)

The user's 23:18 recording showed the pack disappearing and a card over a black background, without the seven-second intro. The previous reduced-motion branch reproduced this exact behavior: phase `hero`, movie time 0, paused and hidden. Removed that branch so an explicit opening always starts the cinematic. Reduced motion still suppresses flashes, particles and card animation. Removed the phase rule hiding the stage background; the movie already renders above it.

Deployed only pack JS/CSS/template at cache version `20261007-motion-2`, preserving ownership/modes and checking all installed SHA256 hashes. Backups: `/tmp/fimobook-motion-20261007-2324/backup`. Service active with no recent error-level journal entries. Public JS SHA256 matches the installed file and public HTML references the new version. Manual Chrome checks with `prefers-reduced-motion: reduce` confirmed local desktop/390px playback and Next transition; the public 390px page showed a visible, unpaused TOTS26 movie at 12.10 seconds with readyState 4. Screenshot: `artifacts/pack-motion-20261007/public-reduced-motion.jpg`. Physical iPhone/Windows playback was not directly checked. No automated tests were added or run.

## Mobile opening effects (2026-10-08)

The user requested visible effects on iPhone, including the reduced-motion path that previously disabled them. Explicit openings now retain effects in both modes. `data-effects=gentle` uses an opacity glow capped at .28, a nearly stationary ring, 18 small slow sparkles and a card fade without zoom or animated filters. Idle floating and other large decorative movements remain suppressed by reduced motion. The mode follows preference changes without changing video playback.

The normal mobile path uses a dimmer glow and an opening-pack animation with only opacity/transform. Particle painting is capped at 24 frames per second on mobile (30 on desktop), with 28 normal mobile dots or 80 desktop dots and a canvas width cap of 960/1536 pixels. Bursts last 1.1 seconds in gentle mode or 1.5 seconds otherwise. There is only one particle animation; replacement, cancellation and hidden-page transitions cancel and clear it. The existing single native cinematic and its decoding path remain unchanged.

Deployed exactly JS/CSS/pack template at `20261008-effects-1`; SHA256 checked, ownership/modes preserved, backups in `/tmp/fimobook-pack-effects-20261008-0010/backup`. Service active with no recent error-level journal entries; public CSS SHA256 matches the installed file and public HTML loads the new JS version.

Manual Chrome inspection at 390px confirmed both normal mobile and reduced-motion gentle modes, visible sparkles/glow in screenshots, correct card animation names, continuing scoreboard playback and local Next/replay transitions. The public reduced-motion page used a 331×186 particle canvas, `gentle-opening-glow`, a visible flash layer, and an unpaused scoreboard at 15.87 seconds. Screenshots are under `artifacts/pack-effects-20261008/`. Device performance was not benchmarked and a physical iPhone was unavailable. No automated tests were added or run.


## Shop and FV relay refresh (2026-10-08)

Refreshed all STORE and KKAEBI_BAT trees and added the official FV_RELAY category, preserving every nested row and detail page (67 source products; 51 exposed products after existing exclusions). User-provided shop screenshots 7380–7392 establish seven new STORE prices and all 16 relay prices, including free completion rewards. Maple singles cost 100/320/1,250 FV; sets cost 2,400 FV for 30 packs and 5,120 FV for 20; TOP200 costs 15,900 FV; FCA27 144–146 costs 5,900 FV. Four existing monthly prices were reconfirmed; other existing price dates remain unchanged. Expired products no longer present in the official list are removed from the catalog. Existing event prices/art remain intact.

Relay entries are ordered by group/stage, with purchase limits and unlock conditions shown. Stages can be simulated independently; the simulator does not enforce real-game token inventory or purchase limits. Official negative-one guaranteed baton/token leaf rows are allowed only in FV_RELAY and exact known item names. They remain intact in the odds but are excluded from acquired rewards. All other count/probability validation is unchanged. Completion FV rewards remain distinct from MP/player value; returned FV does not reduce gross FV spent in the existing multiplier. Free prices display as 무료.

No automated tests were added or run. Source evidence and candidate review files are stored in /tmp/fcm-pack-update-20261008 and the durable pack-update-20261008 artifact directory.

Deployed five files on 2026-10-08: pack_opener.py, templates/pack_opener.html, static/js/pack-opener.js, static/data/pack_probabilities.json and static/data/pack_shop_prices.json. Existing production hashes matched the captured baseline; ownership/modes were preserved and installed hashes matched. Backups: /tmp/fcm-pack-update-20261008-install/backup. Service active with no recent error-level journal entries. Public 390px UI confirmed all five Maple listings/prices and the FV relay selector.
