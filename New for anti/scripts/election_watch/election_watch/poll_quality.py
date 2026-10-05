"""Source-review facts and coverage, without inventing an accuracy grade."""
from copy import deepcopy
from datetime import date
from .polls import digest, require


def review_fingerprint(row):
    return digest({k: row[k] for k in ('id', 'race_id', 'pollster_group', 'field_start',
                                     'field_end', 'population', 'sample_n', 'answers')})


def source_quality(row, reviews, as_of):
    base = {'verification_level': 'partial', 'methodological_quality': 'unrated',
            'accuracy_grade': None, 'label_ko': '선정 기관 · 집계값 부분 검증',
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
