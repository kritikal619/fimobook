# Code structure (2026-10-11)

This refactor separates presentation and PNG rendering from the largest entry
files. It preserves existing routes, data formats, calculations, script order,
and browser storage keys.

## Where to make changes

| Responsibility | File |
| --- | --- |
| Home/search layout and markup | `templates/search.html` |
| Home/search page styles | `static/css/home-search.css` |
| Player detail layout and markup | `templates/detail.html` |
| Player detail page styles | `static/css/player-detail.css` |
| Detail growth and skill controls | `templates/partials/player_detail/growth_script.html` |
| Detail PNG export and tier voting | `templates/partials/player_detail/export_and_tier_script.html` |
| Detail mobile navigation | `templates/partials/player_detail/navigation_script.html` |
| Detail lazy card backgrounds | `templates/partials/player_detail/lazy_backgrounds_script.html` |
| Squad layout and markup | `templates/squad_maker.html` |
| Squad builder base styles | `static/css/squad-builder.css` |
| Squad growth/editor styles | `static/css/squad-maker.css` (existing) |
| Squad formation, search, layout and persistence | `templates/partials/squad_maker/builder_script.html` |
| Squad per-player growth editor | `static/js/squad-maker.js` (existing) |
| Player statistics PNG renderer and shared summary helpers | `player_stats_card.py` |
| Detail-search query parsing, validation and result ordering | `player_search.py` |
| Search predicates, catalog access and response rendering | `app.py` (`filtered_players`) |
| Isolated local regression runner | `scripts/run_local_tests.py` |
| Test browser session with a real page token | `tests/browser_session.py` |

## Boundaries to preserve

- Script partials are **server-rendered HTML**, including their `<script>` tags.
  They receive the original Jinja context and render in their original positions.
  They are not standalone JavaScript assets: they contain Jinja data expressions.
  Keeping them inline also preserves the builder's existing global lexical
  bindings and the existing HTML-based checks.
- Stylesheet links occupy the original inline styles' positions in the cascade.
  Keep them ahead of the existing page overrides and shared card styles.
  Font and pitch image paths are relative to `static/css/`, so they also work
  when Flask is served under a URL prefix.
- The home and player detail accessibility heading rules remain inline, without
  duplicate rules in the extracted CSS. Hidden headings remain hidden while
  the external stylesheet loads.
- `player_stats_card.py` does not import the Flask app, initialize databases, or
  load the player catalog. Its renderer still receives `root_path` explicitly.
  `app.py` imports the existing helper names so callers retain their interfaces.
  Player comparison and the PNG renderer continue to share the same summary
  weights and numeric helpers.
- This extraction does not change authentication, persistence, background jobs,
  search semantics, or production configuration.

## First extraction: review evidence

Before editing, the four original entry files were copied to a temporary local
directory. Source comparisons checked that the script partials expand to the
original scripts, the extracted CSS preserves its rules and ordering (apart
from the two independent accessibility rules retained inline), and asset URLs
resolve to the same files. Python AST comparisons checked that all 505 original
functions/classes retain their definitions and all other non-import app
statements remain unchanged. Jinja parsing and JavaScript syntax checks covered
the extracted scripts, including missing-player, field-player and goalkeeper
branches.

After the user authorized tests, the 42 related existing tests were run against
both the current files and the pre-extraction snapshot. Both runs had the same
28 passes, 13 failures and one error. Supplying valid browser page tokens in a
test-only client produced the same 34 passes and eight failures on both versions.
Six additional regression tests passed, covering PNG equivalence, local artwork,
PNG route behavior, static assets, rendered scripts and existing access checks.
Details and limits are in `reports/code-structure-verification-20261011.md`.

## Second extraction: search and repeatable tests

`player_search.py` accepts request arguments and explicit option lists. It does
not import Flask, load a catalog, initialize a database or make HTTP requests.
The route retains catalog-dependent predicates, record normalization and HTML
rendering; its body shrank from 356 to 167 lines. Imported helper names and the
`_price_enhance_arg` wrapper preserve existing callers in `app.py`.

Detail-search reversed ranges still produce an error; quick-search reversed
ranges still swap bounds. Unknown skill names keep their existing meaning.
Zero prices remain valid, unavailable prices sort last, and identical keys
retain their input order. Invalid detail queries return before building team
or external career indexes, while preserving the original error precedence.

The regression tests now obtain real session-bound browser tokens instead of
calling protected APIs without a page visit. Stale UI/payload assertions were
updated to the behavior that already existed before the extraction. Renewal
schedule content uses a deterministic fixture, and empty playstyle icons are
counted as HTML images rather than matching duplicated JSON text.

Run the 71 related tests from the repository root:

```sh
venv/bin/python scripts/run_local_tests.py
```

Or select a module:

```sh
venv/bin/python scripts/run_local_tests.py tests.test_player_search
```

The runner uses temporary instance/database paths, disables analytics and
outbound Requests HTTP, and writes `result.json` into its printed temporary
directory. Read API page-token protection remains active. This is a local
Python/Flask suite, not browser end-to-end or live provider validation.

All 71 tests passed against both the pre-search-extraction app and the current
app. An additional snapshot comparison covered 500 deterministic query
combinations with identical rendered contexts. Evidence and limits are in
`reports/search-refactor-verification-20261011.md`.

No production deployment is included. If deploying later, install `app.py`,
the three changed templates and all their extracted modules/assets/partials
together, following the project's deployment instructions.

## Next independent steps

The largest remaining responsibility is the Flask app itself. Extract DB
extensions/models and explicitly controlled initialization before separating
routes into feature blueprints; background jobs currently import that app.
Treat this as a separate change with runtime verification. The squad builder
also still shares global state with its growth editor; introducing an explicit
interface should be a separate behavior-preserving refactor.
