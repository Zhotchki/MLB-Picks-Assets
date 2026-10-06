# MultiSport Pick’em v0.3.1

Dedicated app: https://zhotchki.github.io/MLB-Picks-Assets/multisport/

Source of truth: this directory on main in Zhotchki/MLB-Picks-Assets. This app is separate from the existing MLB app. Future assistant updates can use the connected GitHub tools directly. No copying Apps Script files or manual spreadsheet entries is required for this adapter.

## Automatic operation

`.github/workflows/update-multisport.yml` runs every 15 minutes and when adapter code changes. Scheduled Actions are best effort and can be delayed. It retrieves the existing MLB Apps Script JSON endpoint directly, checks age of BOTH snapshot and underlying projection refresh, validates current games and player identities against MLB StatsAPI, captures the first pregame forecast permanently, grades final batting results, and updates the frontend JSON. Failed network runs leave previous data intact. The UI hides data older than 45 minutes and stale upstream forecasts. MLB’s existing Apps Script refresh is an upstream dependency; this workflow does not install an Apps Script trigger.

`ledger.json` contains model forecasts, not user wagers or personal information. Capture once per game/player/prop/threshold; do not overwrite probabilities after seeing results. Postponed/cancelled games and players with no plate appearances are void. Same-name matching requires a unique identity on the specified team and game. Doubleheaders are excluded until upstream game IDs are available.

Mondays: candidate additive calibration offsets (minimum 50 samples per sport/prop/direction group, 50 pseudo-observations of shrinkage). Requires 200 training forecasts, 50 holdout forecasts, and 10 games. Entire games stay in one side of the chronological split. Candidates need better Brier AND log loss by at least .001; holdout games must be newer than the incumbent's training cutoff. Store review/version; apply a promoted model only to future captures. This is a basic calibration stage, not a proven cross-sport predictive model. Repeated weekly selection still needs independent prospective evaluation.

## Current limits and next implementation

MLB and NFL forecast adapters connected. NBA/NHL remain NOT_CONNECTED. Current MLB Reference Line values are empty; Probability Threshold is a MODEL TARGET, not a Sleeper/platform line. Therefore no playable slips or payouts are offered. Never turn a target into a fictitious line or describe reciprocal probability as an actual payout.

Next: activate and verify the prepared platform feed; attach exact player/event/prop/direction/line/payout identifiers and recalculate probability at that exact line. Then implement mixed-sport slip optimization with no duplicate player, upcoming verified events, provider restrictions, and explicitly qualified joint probabilities. Build NFL, NBA and NHL data adapters separately using expected snaps/minutes/TOI. Until fitted joint dependencies exist, exclude same-event legs rather than inventing correlation coefficients. Do not claim the globally highest win probability from a heuristic search.

Run checks: `python -m unittest discover -s multisport -p 'test_*.py'`; update: `python multisport/update.py`. Runtime uses Python 3.12 stdlib, no credentials or paid dependencies.

## v0.3: NFL adapter and optional platform feed

NFL reads the existing app's JSON endpoint automatically. It imports automatic model targets only, verifies season/week, Eastern-time kickoffs against nflverse, stable GSIS player ID/team against Sleeper roster, availability, expected snaps, and at least four historical games. Four games is a minimum support gate, not calibration proof. Started games and prior-week projections are excluded. NFL results are graded against final scheduled scores plus matching GSIS/season/week/team/opponent stats from nflverse. Missing rows or stats remain pending, never inferred as losses. NFL source failures do not block MLB updates.

Live lines connector: ParlayAPI's documented /v1/sports/{sport}/props endpoint, scoped to Sleeper, for MLB/NFL/NBA/NHL. It is UNCONNECTED until the owner adds PARLAY_API_KEY in repository Actions secrets. Never place the key in source, a public file, or chat. Personal key setup: https://parlay-api.com/ ; repository secret settings: https://github.com/Zhotchki/MLB-Picks-Assets/settings/secrets/actions . Default cadence is two board polls per day per sport, maximum 900 reserved credits/month. Four sports at this cadence use at most 744 credits in a 31-day month before any failures. No automatic pagination, paid subscription, credit purchase, or rate increase. Documentation claims a 1,000-credit free tier; coverage and pricing need confirmation with the actual account. To change cadence/budget, explicitly set PICKEM_REFRESH_MINUTES / PARLAY_MONTHLY_CREDIT_CAP after choosing a suitable plan. Slow default polling intentionally means offers disappear after 15 minutes; it is not a continuous real-time four-sport board.

The live /props path has not been tested against an authenticated account. Contract tests use fixtures. A key is necessary to verify real sport coverage, projection types, periods, matching and completeness headers. Board diagnostics preserve truncation/degradation/has-more flags; do not claim exhaustive coverage. No key: forecasts, result grading and model review continue without live-line requests.

Match only a named standard, FULL-game offer with reported kickoff, canonical event ID, known market, unique player identity, matching teams, and observation age <=15 minutes. Match the EXACT model line; no interpolation or assigning a forecast probability to a different platform line. Price fields from DFS midpoint/effective conversions are not used as estimated win probabilities or payouts. Unknown offer type, period or time is excluded. NBA/NHL remain without forecast adapters even if their boards are observed.

Slip search supports 2/3/4/5/6/8 legs, 200-offer pool, 128 beam states per leg count and up to five returned slips per size. No repeated player or game; Sleeper offers only. Joint probability assumes independence across games, excludes same-game combinations, and is explicitly labeled an estimate. This is a bounded search of matched available offers, not a proven global optimum or learned correlation model. Source payout unavailable means no payout is displayed. The result ledger remains a forecast ledger; provider-specific wager/slip settlement needs a separate ledger in a future release.

## v0.3.1: independent refresh and browser expiry

MLB collection and grading failures are isolated from NFL. An unavailable MLB source publishes an explicit unavailable status, excludes its forecasts for this run, preserves existing immutable ledger entries, and still runs NFL collection/grading. Unknown results stay pending. Browser offer eligibility rechecks the observation timestamp (15-minute maximum), snapshot age (45-minute maximum), kickoff and per-sport source status at generation and every 15 seconds, including already displayed slips. NFL support counts are labeled historical games, not calibration samples.

NHL official schedule/roster/player-log endpoint requests returned HTTP 403 during the October 5 implementation check. No NHL data or probability is fabricated. NBA and NHL adapters remain pending. Platform key status was still NEEDS_API_KEY in the latest automatic run.
