"""Standalone review preview; does not change or connect the production UI."""
import argparse
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from option_direction_model import read

NAMES={'opening_up':'시작 상방','closing_up':'종가 상방','direction_persists':'종가까지 방향 유지','opening_extends':'시가 이후 추가 진행'}


def render(payload):
    esc=lambda x:html.escape(str(x))
    replay=payload['status']=='retrospective_replay'
    status='과거 재생 · 실제 사전 예측 아님' if replay else ('자료 대기' if payload['status']=='unavailable' else '연구 참고 점수')
    generated=datetime.fromisoformat(payload['generated_at']).astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST')
    cards=[]
    for card in payload['cards']:
        rows=[]
        for key in NAMES:
            score=card['scores'][key];p=score['score_0_100'];reference=score['information_state']=='recent_base_rate_only'
            tone='reference' if reference else ('up' if p>50 else 'down' if p<50 else 'reference')
            if reference:label='최근 빈도만 반영'
            elif key in ['opening_up','closing_up']:label='상방 기울기' if p>50 else '하방 기울기' if p<50 else '균형'
            elif key=='direction_persists':label='유지 쪽' if p>50 else '반전 쪽'
            else:label='추가 진행 쪽' if p>50 else '추가 진행 약함'
            rows.append(f'<section><div class="row"><span>{NAMES[key]}</span><strong>{p:.1f}%</strong></div><div class="track"><i></i><b class="{tone}" style="left:{min(100,max(0,p)):.2f}%"></b></div><small class="{tone}">{label}</small></section>')
        cards.append(f'<article><h2>{esc(card["label_ko"])}</h2>{"".join(rows)}</article>')
    content=''.join(cards) or '<article><h2>점수 미발행</h2><p>대상 거래일에 필요한 자료 또는 마감 시각 조건이 아직 충족되지 않았습니다.</p></article>'
    warning='<p class="warning">이 점수는 과거 입력으로 재생한 화면 연결 예시입니다. 실제 해당일 개장 전에 발행한 예측이 아닙니다.</p>' if replay else ''
    refresh='<p class="warning">새 자료 갱신에 실패했습니다. 표시된 같은 거래일의 기존 예측 시각을 확인하세요.</p>' if payload['refresh']['status']=='unavailable' and payload['cards'] else ''
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>개장 전 방향 점수 검토</title>
<style>body{{margin:0;background:#0c1422;color:#edf2fa;font:16px system-ui,sans-serif}}main{{max-width:1100px;margin:48px auto;padding:0 24px}}.badge{{color:#ffce82;font-size:14px}}h1{{font-size:30px;margin:12px 0}}p{{color:#a8b8ce;line-height:1.6}}.warning{{background:#33291d;color:#ffe0ae;border-radius:8px;padding:14px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin:28px 0}}article{{background:#142136;border:1px solid #2b3b52;border-radius:14px;padding:22px}}h2{{font-size:22px;margin:0 0 24px}}section{{margin:0 0 26px}}.row{{display:flex;justify-content:space-between;gap:12px;font-size:14px}}strong{{font-size:20px}}.track{{height:6px;background:#27354b;position:relative;margin:16px 0 10px;border-radius:6px}}i{{position:absolute;left:50%;top:-5px;height:16px;border-left:1px solid #9aacc6}}b{{position:absolute;top:-3px;width:12px;height:12px;border-radius:50%;transform:translateX(-50%)}}b.up{{background:#ff858c}}b.down{{background:#85baff}}b.reference{{background:#9aacc6}}small.up{{color:#ffb1b6}}small.down{{color:#a7ceff}}small.reference{{color:#a8b8ce}}footer{{color:#a8b8ce;font-size:13px;line-height:1.7}}</style>
<main><div class="badge">{status}</div><h1>개장 전 방향 참고 점수</h1><p>대상 {esc(payload['target_date'])} · 한국 입력 {esc(payload['KR_source_date'])} · 미국 입력 {esc(payload['US_source_date'])}<br>생성 {esc(generated)}</p>{warning}{refresh}<div class="cards">{content}</div><footer>각 막대의 가운데 선은 50%입니다. 시작·종가 상방 확률과 유지·추가 진행 확률은 서로 다른 사건입니다.<br>모델 {esc(payload['model_id'][:16])} · 학습 결과 기준 {esc(payload['trained_through'])} · 본 화면은 연결 검토용이며 운영 UI에는 아직 연결되지 않았습니다.</footer></main></html>'''


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(render(read(args.input)),encoding='utf-8')
