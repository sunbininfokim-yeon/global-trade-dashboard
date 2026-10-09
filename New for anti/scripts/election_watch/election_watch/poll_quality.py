"""Source-review facts and coverage, without inventing an accuracy grade."""
from copy import deepcopy
from datetime import date
import math
from urllib.parse import urlparse
from .polls import digest, require


def review_fingerprint(row):
    return digest({k: row[k] for k in ('id', 'race_id', 'pollster_group', 'field_start',
                                     'field_end', 'population', 'sample_n', 'answers')})


def answer_correction_fingerprint(raw):
    return digest({k: raw.get(k) for k in ('id', 'subject', 'poll_type', 'pollster', 'url',
        'start_date', 'end_date', 'created_at', 'population', 'sample_size', 'answers',
        'seat_name', 'sponsors', 'internal', 'partisan')})


def corrected_provider_answers(raw, review, as_of):
    """Correct only exact, unchanged records whose every candidate value was reviewed."""
    correction = review.get('provider_answer_correction')
    if not correction:
        return raw, None
    require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of), 'future_quality_review')
    require(correction['provider_snapshot_sha256'] == answer_correction_fingerprint(raw),
            'provider_answer_correction_snapshot_changed')
    admission = review.get('admission', {})
    require(admission.get('provider_url') == raw.get('url') and admission.get('pollster') == raw['pollster']
            and admission.get('source_role') in ('pollster_primary', 'commissioner_primary')
            and review.get('sources') and review.get('disclosure_review'), 'unverified_answer_correction')
    values = review['primary_toplines']
    names = [a['choice'] for a in raw['answers']]
    require(len(names) == len(set(names)) and set(names) == set(values), 'incomplete_answer_correction_review')
    overrides = correction['overrides']
    require(overrides and set(overrides) <= set(names), 'unsupported_answer_correction')
    require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100 for v in values.values())
            and sum(values.values()) <= 102, 'invalid_primary_answer_values')
    corrected = deepcopy(raw)
    for answer in corrected['answers']:
        name = answer['choice']
        if name in overrides:
            require(overrides[name] == values[name], 'answer_correction_primary_mismatch')
            answer['pct'] = overrides[name]
        require(abs(answer['pct'] - values[name]) <= .51, 'uncorrected_primary_answer_mismatch')
    return corrected, {'status': 'reviewed_primary_answer_correction',
        'reviewed_on': review['reviewed_on'], 'provider_snapshot_sha256': correction['provider_snapshot_sha256'],
        'provider_values': {a['choice']: a['pct'] for a in raw['answers'] if a['choice'] in overrides},
        'primary_values_used': deepcopy(overrides), 'sources': review['sources'], 'basis_ko': correction['basis_ko']}


def corrected_provider_source(raw, review, as_of):
    """Restore an absent URL only for an exact, primary-reviewed API snapshot."""
    correction = review.get('provider_source_correction')
    if not correction:
        return raw, None
    require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of), 'future_quality_review')
    require(not review.get('provider_answer_correction'), 'combined_provider_corrections_require_review')
    require(correction['provider_snapshot_sha256'] == answer_correction_fingerprint(raw),
            'provider_source_correction_snapshot_changed')
    require(raw.get('url') in (None, '', '[null]') and
            correction.get('original_provider_url') == raw.get('url'), 'provider_source_not_missing')
    admission = review.get('admission', {})
    primary = correction['primary_url']
    parsed = urlparse(primary)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
            and primary in review.get('sources', []) and admission.get('provider_url') == primary
            and admission.get('source_role') in ('pollster_primary', 'commissioner_primary')
            and admission.get('pollster') == raw['pollster'] and review.get('disclosure_review')
            and len(review.get('primary_toplines', {})) >= 2, 'unverified_source_correction')
    corrected = deepcopy(raw)
    corrected['url'] = primary
    return corrected, {'status': 'reviewed_missing_primary_link', 'reviewed_on': review['reviewed_on'],
        'provider_snapshot_sha256': correction['provider_snapshot_sha256'],
        'original_provider_url': raw.get('url'), 'primary_url': primary,
        'sources': deepcopy(review['sources']), 'basis_ko': correction['basis_ko']}


def source_quality(row, reviews, as_of):
    base = {'verification_level': 'partial', 'methodological_quality': 'unrated',
            'accuracy_grade': None, 'label_ko': '출처 연결 · 집계값 부분 검증',
            'basis_ko': '기관·원문 도메인·대진·기간·표본·모집단 검사 통과. 원문별 방법론과 수치 재검증 미완료.',
            'missing_fields': ['margin_of_error_pp', 'question_sample_n', 'primary_values_rechecked']}
    review = reviews.get(row['id'])
    if not review:
        return base
    require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of), 'future_quality_review')
    require(review['snapshot_sha256'] == review_fingerprint(row), 'quality_review_snapshot_changed')
    for name, value in review['primary_toplines'].items():
        observed = next((a['pct'] for a in row['answers'] if a['name'] == name), None)
        require(observed is not None and abs(observed - value) <= .51, 'primary_topline_mismatch')
    return {**base, 'verification_level': 'primary_toplines_checked',
            'label_ko': '원문 수치 대조 완료 · 정확도 등급 미평가',
            'reviewed_on': review['reviewed_on'], 'review_sources': review['sources'],
            'primary_toplines': review['primary_toplines'],
            'question_sample_n': review.get('question_sample_n'),
            'disclosure_review': deepcopy(review.get('disclosure_review', {})),
            'reported_precision': deepcopy(review.get('reported_precision')),
            'ballot_format': review.get('ballot_format', 'not_reviewed'),
            'sponsor_review': deepcopy(review.get('sponsor_review', {})),
            'basis_ko': '수기 검토한 원문과 현 집계 레코드 대조. 공개 항목 검토이며 AAPOR 인증·정확도·통계적 유의성 평가가 아닙니다.',
            'missing_fields': review.get('missing_fields', []),
            'limitations_ko': review['limitations_ko']}


def evidence_context(pollster_count, agreement_fraction, conflicting=()):
    """Descriptive coverage and agreement, never a high/medium/low quality score."""
    coverage = 'none' if not pollster_count else 'single_source' if pollster_count == 1 else 'multiple_sources'
    return {'level': 'unrated', 'grade': None, 'label_ko': '품질 등급 미평가',
            'coverage': coverage,
            'coverage_label_ko': {'none': '조사 없음', 'single_source': '단일 기관 참고',
                                  'multiple_sources': '복수 기관 집계'}[coverage],
            'independent_pollster_count': pollster_count,
            'agreement_fraction': agreement_fraction if pollster_count else None,
            'conflicting_pollsters': list(conflicting),
            'basis_ko': '기간 내 기관별 최신 1건의 수와 동일 후보 수치상 우세 비율. LV/RV 분리.',
            'limitations_ko': '기관 수·일치도만으로 조사 품질·정확도·통계적 신뢰수준·당선확률을 평가하지 않습니다.'}


def ranked_choice_question(raw, review, race, as_of):
    """Reference-only questions tied to an exact reviewed RCV release.

    Missing candidates are allowed only in a reviewed final simulation or forced
    pair. No question kind becomes a winner or votes in ordinary lead counts.
    """
    if race.get('ballot_system') != 'ranked_choice':
        require(not review.get('ranked_choice_question'), 'RCV review outside ranked ballot')
        return None
    q = review.get('ranked_choice_question')
    require(q and review.get('provider_record_sha256') == answer_correction_fingerprint(raw),
            'ranked_choice_question_not_reviewed')
    require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of), 'future_quality_review')
    admission = review.get('admission', {})
    require(admission.get('signal_eligible') is False
            and 'ranked_choice_separate_question_reference' in admission.get('signal_exclusion_reasons', [])
            and admission.get('source_role') in ('pollster_primary', 'commissioner_primary')
            and review.get('disclosure_review') and review.get('sources'), 'RCV requires exact reference review')
    require(q.get('kind') in ('first_preference', 'simulated_final_round', 'forced_two_candidate')
            and q.get('question') and q.get('label_ko'), 'invalid ranked choice question')
    names = [a['choice'] for a in raw['answers']]
    require(len(names) == len(set(names)) and set(names) == set(review['primary_toplines'])
            and set(names) == set(q['compared_candidates'])
            and all(n in race['candidates'] for n in names), 'unreviewed ranked choice comparison')
    canonical = lambda n: race['candidates'][n].get('canonical_name', n)
    full = {canonical(n) for n in race['required_candidates']}
    compared = {canonical(n) for n in names}
    require(compared <= full and (compared == full if q['kind'] == 'first_preference'
                                 else len(compared) == 2), 'ranked choice field mismatch')
    return {**deepcopy(q), 'election_result': False, 'aggregation_eligible': False}
