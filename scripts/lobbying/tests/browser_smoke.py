"""Run against preview.mjs with actual source snapshot; does not validate deployment."""
import json
import argparse
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',default=str(Path(tempfile.gettempdir())/'lobbying-browser-qa'))
args=parser.parse_args()
output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    browser = p.chromium.launch(headless=True, executable_path=chrome if Path(chrome).exists() else None)
    results = []
    for width in (1440, 390):
        page = browser.new_page(viewport={'width':width,'height':1000})
        errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8769/policy/us/lobbying')
        page.get_by_role('heading', name='로비·사안', exact=True).wait_for()
        page.locator('[data-results] table').wait_for()
        assert page.locator('tbody tr').count() == 25
        page.locator('[data-page="next"]').click()
        page.wait_for_function("document.querySelector('[data-page-label]').textContent === '2'")
        page.locator('[name="q"]').fill('not_a_real_company_739274')
        page.locator('[data-filters]').evaluate('(f)=>f.requestSubmit()')
        page.get_by_text('이 조건으로 수집된 문서가 없습니다.', exact=False).wait_for()
        page.locator('[name="q"]').fill('')
        page.locator('[data-filters]').evaluate('(f)=>f.requestSubmit()')
        page.locator('[data-results] table').wait_for()
        page.screenshot(path=str(output/f'lobbying-{width}.png'),full_page=True)
        page.locator('[data-case]').click()
        page.get_by_role('heading',name='쿠팡의 한국 개인정보 규제와 미국 통상 대응',exact=True).wait_for()
        assert page.get_by_text('Greenoaks Capital Partners',exact=False).count() >= 1
        assert page.get_by_text('개인정보 분쟁 대응 로비라고 확인할 수 없습니다.',exact=False).count() == 1
        page.reload()
        page.get_by_role('heading',name='쿠팡의 한국 개인정보 규제와 미국 통상 대응',exact=True).wait_for()
        page.get_by_role('button',name='← 신고 검색').click()
        page.locator('[data-results] table').wait_for()
        page.locator('[data-record]').first.click()
        page.get_by_role('heading',name='정책 연결',exact=True).wait_for()
        assert page.get_by_role('link',name='공식 원문',exact=False).count()==1
        assert not errors, errors
        results.append({'width':width,'page_errors':errors,'navigation':'list/page/search/case/reload/record'})
        page.close()
    browser.close()
    (output/'browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))
