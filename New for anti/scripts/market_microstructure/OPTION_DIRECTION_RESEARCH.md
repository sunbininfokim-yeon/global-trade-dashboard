# Fixed-model direction forecasts

The first target is KODEX 200 (069500) next KRX session close versus that
session's open, NOT next close versus today's close. `UP` means close > open;
`DOWN` includes unchanged close. This model does not forecast return magnitude.

The frozen option-only logistic model emits an estimated probability and
UP/DOWN at 0.5. It remains `research_only`: current retrospective tests do
not justify promotion to a trading signal, and probabilities are uncalibrated.
Availability of historical EOD options before next open and adjusted OHLC
common factors are assumptions. No UI or daily workflow is connected by this PR.

## Commands

From `New for anti/scripts/market_microstructure`, install optional dependencies
from `requirements-direction-research.txt` into a suitable research environment.

```sh
python option_direction_model.py evaluate --output research-evaluation.json
python option_direction_model.py train --as-of 2026-10-30 --output models/new-version.json
python option_direction_model.py predict --model models/option_direction_v1_20261030.json --output forecast-20261030.json
```

- `train` is an explicit model update. It refuses an existing model path. Training
  includes only labelled outcomes on/before the cutoff; the source day of the
  final training example is earlier than its target day.
- `predict` never trains or recalculates model scalers. Without `--as-of` it uses
  the latest claimed call/put date, including an incomplete latest date. Missing
  observed inputs in the required 61-session window yield `unavailable`, null
  probability and null direction, without silently using an older source day.
- New inputs change features and predictions, not model coefficients. The
  algorithm and feature schema must be versioned along with the model.
- Keep each forecast in a distinct source-date file. Repeating the identical
  request preserves the existing file and timestamp. Revised inputs or a new
  model require a new output path, preserving the original forecast.
- Each output records model ID, training cutoff, source date, next-session date,
  generation timestamp, input hash, feature values and limitations. Historical
  forecasts made after their outcome must remain retrospective research.
- Runtime/calendar version is recorded; a changed calendar version requires
  review rather than silently changing the frozen model's feature windows.

## Experiments

Four fixed classifiers share exactly the same valid target dates: historical
class prior, price-only, option-only, price+option. Features are prior-60-session
relative ranks of call/put foreign net premium flows (net / market buy value),
their five-session means, and price momentum/volatility for the comparison
models. Flow premium differences are not delta-adjusted directional exposure.
The price features use only prices through the source day.

Each expanding fold fits through the previous quarter, excluding examples whose
outcome crosses the evaluation boundary. Scalers fit only training observations.
C=1 and decision threshold=0.5 are fixed. Direction accuracy, Brier/log loss,
quarter/year results, exposure, illustrative long-only returns, drawdown and
5/10/20bps roundtrip sensitivity are retained. DOWN does not initiate a short.
A paired 5-session block bootstrap estimates uncertainty in combined-minus-price
Brier loss; this is exploratory and does not adjust for all previously tried ideas.

## Calendar audit limitation

The Python 3.9 environment resolved exchange_calendars 4.5.6. Its XKRX calendar
includes six dates absent from BOTH option and ETF files: 2024-10-01, 2025-01-27,
2025-06-03, 2026-05-25, 2026-06-03, 2026-07-17. These are calendar disagreements,
NOT proven missing trading data. No source records are manufactured or removed.
Complete-session filtering conservatively excludes windows crossing those dates;
the evaluation manifest lists them explicitly. Calendar reconciliation must precede
any live promotion or claims of full common coverage. Relevant first-party notices:

- https://www.next-securities.com/board/boardDetail.do?bbsCategory=NT01&bbsId=BBSMSTR_000000000240&content=4000198&nttId=11720
- https://www.next-securities.com/board/boardDetail.do?bbsCategory=NT01&bbsId=BBSMSTR_000000000240&content=4000383&nttId=11917

Calendar API: https://github.com/gerrymanoim/exchange_calendars
Estimator API: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html

## Claude integration handoff

After the daily 15007 board update and validation, invoke only `predict` with
the frozen model path and a new forecast file named by source date. Preserve that
file in GitHub and show UP/DOWN, target definition/date, estimated probability,
model version and `research_only` label in the UI. On unavailable or process error,
do not display yesterday's prediction as today's. Do not schedule `train` daily.
Model updates require a new artifact and an explicit change of the model path.
Workflow and UI changes belong to Claude; no production integration is claimed here.
