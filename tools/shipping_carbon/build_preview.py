"""Freeze collected observations into a self-contained conversation preview; never invent data."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(output):
    prices = json.loads((ROOT / "source_data/reference_prices.json").read_text())
    oi = ROOT / "source_data/market_structure.json"
    audit = ROOT / "source_data/fueleu_audit.json"
    demo = ROOT / "source_data/combined_example.json"
    payload = {"prices": prices, "market_structure": json.loads(oi.read_text()) if oi.exists() else {"status": "not_collected", "records": []},
               "fueleu_audit": json.loads(audit.read_text()) if audit.exists() else {"status": "not_collected"}}
    for s in payload["fueleu_audit"].get("sources", {}).values():
        s.pop("file", None)
    if demo.exists():
        payload["combined_demo"] = json.loads(demo.read_text())
    page = (ROOT / "market.html").read_text()
    body = page.split('<body>', 1)[1].split('</body>', 1)[0]
    body = body.replace('<script type="module" src="/market-ui.js"></script>', '')
    # A frozen preview cannot navigate to the local app's relative route.
    body = body.replace('<a href="/">해운 계약·날짜별 자금 계산 열기</a>', '해운 계약·날짜별 자금 계산은 로컬 도구에서 제공')
    body = body.replace('<button type="submit">총비용·자금 비교</button>', '<button type="submit" disabled>로컬 도구에서 계산</button>')
    body = body.replace('id="cd-combined-example">', 'id="cd-combined-example" disabled>')
    css = (ROOT / "market.css").read_text().replace(':root{color-scheme:light dark}body{margin:0}', '')
    math = re.sub(r'^export ', '', (ROOT / "market-math.mjs").read_text(), flags=re.M)
    ui = (ROOT / "market-ui.js").read_text().split('\n', 1)[1]
    encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    ui = re.sub(r'// DATA_LOADER_START.*?// DATA_LOADER_END', lambda _: f"init({encoded});", ui, flags=re.S)
    ui = re.sub(r'// API_COMBINED_START.*?// API_COMBINED_END',
                lambda _: "async function requestCombined(){throw Error('입력 변경 계산은 로컬 도구에서 제공됩니다');}", ui, flags=re.S)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('<style>\n' + css + '\n</style>\n' + body + '\n<script type="module">\n' + math + '\n' + ui + '\n</script>\n')
    if output.stat().st_size >= 1_000_000:
        raise ValueError('Preview exceeds size limit')
    return output


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    print(build(p.parse_args().output))
