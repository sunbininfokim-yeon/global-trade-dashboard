// Runs the scenario engine's actual computation (runScenario /
// compareScenarioVariants) off the main thread, so a heavy calculation --
// e.g. the block-bootstrap mean CI, which resamples the return series
// hundreds of times -- doesn't freeze the scenario-backtest tab while it
// runs. scenario.mjs already has zero network/storage I/O by design; this
// worker doesn't change that contract, it only crosses the worker boundary
// with the same plain-JSON input/variants the main thread already builds
// (portfolio.js's scenarioBuildInput()) and posts the plain-JSON result back.
import { runScenario, compareScenarioVariants } from './scenario.mjs';

self.onmessage = (e) => {
    const { id, kind, input, variants } = e.data;
    try {
        if (kind === 'run') {
            self.postMessage({ id, ok: true, result: runScenario(input) });
        } else if (kind === 'compare') {
            const base = runScenario(input);
            const comparison = compareScenarioVariants(input, variants);
            self.postMessage({ id, ok: true, result: { base, comparison } });
        } else {
            throw new Error(`알 수 없는 계산 요청입니다: ${kind}`);
        }
    } catch (err) {
        self.postMessage({ id, ok: false, error: err.message || String(err) });
    }
};
