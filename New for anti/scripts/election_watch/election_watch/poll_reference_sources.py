"""Publisher-identified API observations awaiting individual release review.

A source identity permits reference display, never votes in a polling lead.
Exact release reviews retain precedence. Shared document hosts need bounded
paths/URLs; an API-supplied trust flag cannot approve itself.
"""
from copy import deepcopy
from datetime import date
import re
from urllib.parse import urlparse
from .polls import require

SHARED_HOSTS=frozenset(('docs.google.com','drive.google.com','static1.squarespace.com',
    'www.documentcloud.org','s3.documentcloud.org','x.com','bsky.app'))


def reference_source(raw, policy, as_of):
    entry=policy.get('reference_sources',{}).get(raw.get('pollster'))
    if not entry:return None
    # Historical replays must not consume later source approval or stop the API.
    if date.fromisoformat(entry['reviewed_on'])>date.fromisoformat(as_of):return None
    require(entry['reference_only'] is True and entry['group'] and entry['evidence']
        and entry['source_role'] in ('pollster_primary','commissioner_primary','research_institution'),
        'invalid_reference_source_policy')
    url=raw.get('url');u=urlparse(url if isinstance(url,str)else'')
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):return None
    if u.hostname not in entry['hosts']:return None
    exact=url in entry.get('approved_urls',[])
    patterns=entry.get('url_patterns',[])
    matched=any(re.fullmatch(pattern,url)for pattern in patterns)
    # Shared storage/social sites can never be approved as whole domains.
    bounded=(u.hostname in SHARED_HOSTS or u.hostname.endswith('.cloudfront.net'))
    if bounded and not (exact or matched):return None
    if (entry.get('approved_urls')or patterns) and not (exact or matched):return None
    require(all(urlparse(e['url']).scheme=='https' and e.get('sha256') and e.get('checked_at')
                for e in entry['evidence']),'missing_reference_publisher_evidence')
    return {'group':entry['group'],'methodology_url':entry['evidence'][0]['url'],
        'reference_only':True,'reference_policy':deepcopy(entry)}


def reference_quality(quality, source, raw):
    entry=source['reference_policy']
    missing=set(quality.get('missing_fields',[]))|{'individual_release_values_and_methods_recheck'}
    if raw.get('sample_size') is None:missing.add('sample_n')
    return {**quality,'label_ko':'발표 주체 확인 · 개별 원문 검토 대기',
        'accuracy_grade':None,'methodological_quality':'unrated',
        'basis_ko':'검토한 조사기관·대학·의뢰 언론과 URL 범위가 일치한 API 전달값. 해당 발표의 문항·수치·방법 재검증 전이므로 우세 합계에서 제외합니다.',
        'missing_fields':sorted(missing),
        'publisher_reference_review':{'reviewed_on':entry['reviewed_on'],'source_role':entry['source_role'],
            'group':entry['group'],'evidence':deepcopy(entry['evidence']),
            'reference_only':True,'api_internal':raw.get('internal'),'api_partisan':raw.get('partisan')},
        'limitations_ko':'기관명 등록 여부만으로 버리지 않고 참고 자료로 보존한 관측입니다. 개별 발표 검증·독립성·정확도 인증이나 당선확률이 아닙니다.'}
