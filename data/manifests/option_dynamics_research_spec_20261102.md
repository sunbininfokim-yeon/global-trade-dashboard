# OI/IV dynamics and calibrated direction — specification before results

- Input ref: f2c834378086725d6951a3cb837d3beae6d05cdb. Research only; frozen artifact unchanged.
- Target: 069500 next KRX session close > open. Flat belongs to DOWN.
- Same-date comparisons, same calendar overlay as the preceding research.
- Baseline: 6 price and 4 option-flow features already specified.
- Levels comparator: baseline plus the 5 existing supplemental level features.
- Dynamics candidate: baseline plus normalized futures/institution flows, same-contract
  one-session log changes in call OI, put OI and futures OI, IV change, and one fixed
  interaction (current ETF intraday return times normalized foreign futures flow).
- OI/IV changes require the immediately preceding KRX session and unchanged option
  expiry/futures contract. No differences across rolls; no missing-value imputation.
- Exact days-to-expiry and historical strike IV skew are unavailable in the public
  panel; do not approximate them using month labels or latest profile.
- Outer evaluation: expanding quarterly from 2022. Last six calendar months of
  each training period are reserved for calibration; base/scalers fit on earlier
  rows only. Both label boundaries are purged. At least 250 base and 60 calibration
  rows and both classes in each are required.
- Base model: logistic C=1. Calibration: sigmoid of base score with nonnegative
  slope, unpenalized intercept and fixed slope L2 penalty 1/2. Fit only calibration
  scores. Keep base and calibrator fixed for the whole evaluation quarter.
- Compare raw and calibrated baseline/levels/dynamics against earlier-base and recent
  calibration-period class priors. Report accuracy, Brier, log loss, reliability
  bins, per-year results and illustrative costs. No threshold/feature/C search.
- No promotion on accuracy alone or on improvement over an uncalibrated model.
  Candidate must show incremental information versus same-date class priors and
  baseline, with uncertainty and multiple historical trials disclosed.
- First run lag=0. If incremental skill is unproven, diagnose lag=1 only: keep source
  KRX dates unchanged; use prior-session nonprice features to forecast the following
  session after the current decision day. This is a delayed-information test, not
  a verified UTC/KST correction. No future shift or best-lag selection.
- Any useful retrospective result is only a prospective-test candidate. Actual
  release requires reviewed source availability and a new explicit model version.

## Surface extension (specified after locating raw fields, before surface outcomes)

- Existing private snapshot 3a27fa40 has 94 monthly chain parts (20.21MB compressed)
  and per-strike IV, contract code, month and session. No new KRX queries.
- Extract regular-session observed IV only, preserve raw hashes and selected quote
  support, and reference same-day KOSPI200 index close (not a different-expiry forward).
- One baseline+surface candidate: put 95%-moneyness IV minus ATM-put IV, call
  105%-moneyness IV minus ATM-call IV, ATM-put IV minus ATM-call IV; /100 units.
- Select nearest quoted strike, max 0.015 absolute moneyness error. IV valid in
  source percent range [1,150]. No interpolation or inferred exact expiry dates.
- Use existing public front-month tag to select expiry; do not merge different
  monthly or weekly chains. Not a 25-delta risk reversal or foreign exposure.
- Compare baseline versus surface on surface-complete dates with the same
  independent six-month calibration scheme. Report every result, no best-strike search.
