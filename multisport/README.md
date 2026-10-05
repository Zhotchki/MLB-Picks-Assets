# MultiSport Pick’em v0.2.0

Dedicated app: https://zhotchki.github.io/MLB-Picks-Assets/multisport/

Source of truth: this directory on main in Zhotchki/MLB-Picks-Assets. This app is separate from the existing MLB app. Future assistant updates can use the connected GitHub tools directly. No copying Apps Script files or manual spreadsheet entries is required for this adapter.

## Automatic operation

`.github/workflows/update-multisport.yml` runs every 15 minutes and when adapter code changes. Scheduled Actions are best effort and can be delayed. It retrieves the existing MLB Apps Script JSON endpoint directly, checks age of BOTH snapshot and underlying projection refresh, validates current games and player identities against MLB StatsAPI, captures the first pregame forecast permanently, grades final batting results, and updates the frontend JSON. Failed network runs leave previous data intact. The UI hides data older than 45 minutes and stale upstream forecasts. MLB’s existing Apps Script refresh is an upstream dependency; this workflow does not install an Apps Script trigger.

`ledger.json` contains model forecasts, not user wagers or personal information. Capture once per game/player/prop/threshold; do not overwrite probabilities after seeing results. Postponed/cancelled games and players with no plate appearances are void. Same-name matching requires a unique identity on the specified team and game. Doubleheaders are excluded until upstream game IDs are available.

Mondays: candidate additive calibration offsets (minimum 50 samples per sport/prop/direction group, 50 pseudo-observations of shrinkage). Requires 200 training forecasts, 50 holdout forecasts, and 10 games. Entire games stay in one side of the chronological split. Candidates need better Brier AND log loss by at least .001; holdout games must be newer than the incumbent's training cutoff. Store review/version; apply a promoted model only to future captures. This is a basic calibration stage, not a proven cross-sport predictive model. Repeated weekly selection still needs independent prospective evaluation.

## Current limits and next implementation

MLB forecasts only. NFL/NBA/NHL intentionally marked NOT_CONNECTED. Current MLB Reference Line values are empty; Probability Threshold is a MODEL TARGET, not a Sleeper/platform line. Therefore no playable slips or payouts are offered. Never turn a target into a fictitious line or describe reciprocal probability as an actual payout.

Next: connect a permitted automatic platform board/feed; attach exact player/event/prop/direction/line/payout identifiers and recalculate probability at that exact line. Then implement mixed-sport slip optimization with no duplicate player, upcoming verified events, provider restrictions, and explicitly qualified joint probabilities. Build NFL, NBA and NHL data adapters separately using expected snaps/minutes/TOI. Until fitted joint dependencies exist, exclude same-event legs rather than inventing correlation coefficients. Do not claim the globally highest win probability from a heuristic search.

Run checks: `python -m unittest discover -s multisport -p 'test_*.py'`; update: `python multisport/update.py`. Runtime uses Python 3.12 stdlib, no credentials or paid dependencies.
