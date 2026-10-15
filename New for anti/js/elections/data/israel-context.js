import { selectedSeatSum } from './israel-analysis.js';

const aliases = { 'דרך': '야샤르', 'מחל': '리쿠드', 'רק': '비야하드', 'אמת': '민주당',
    'ל': '이스라엘 베이테누', 'ג': '통합토라유다', 'ודם': '공동명부', 'שס': '샤스',
    'ב': '오츠마 예후디트', 'ט': '종교시온주의·제후트', 'עם': '라암', 'ך': '암하 이스라엘',
    'די': '예비군·신경제', 'כן': '청백당', 'זך': '하레디 공중', 'ני': '노암', 'י': '이스라엘 우선' };

// The browser reads saved translations only; credentials and model calls stay offline.
export const koreanText = (board, source, fallback = '한국어 설명 미확인') => {
    if (!source) return fallback;
    return board.localization?.translations?.find((row) => row.source === source)?.ko || fallback;
};
export const partyProfile = (board, id) => {
    const list = board.lists.find((row) => row.id === id);
    const context = board.coalition_context?.parties?.find((row) => row.list_id === id);
    const group = board.coalition_context?.groups?.find((row) => row.id === (context?.group || 'independent'));
    return { id, list, group: group?.id || 'independent', color: group?.color || '#ba9bf7',
        name: aliases[list?.ballot] || koreanText(board, list?.name_he, '명부 이름 미확인'),
        leader: koreanText(board, context?.leader || list?.leader_as_written, '대표 인물 미확인'),
        description: koreanText(board, context?.description, '보도 명부 · 인물 소개 확인 중'),
        sourceIds: context?.source_ids || [],
        note: koreanText(board, context?.coalition_note, '연정 참여 입장 미확인'),
    };
};
export const personProfile = (board, name) => {
    const party = board.coalition_context?.parties?.find((row) => row.leader === name);
    if (party) return { name: partyProfile(board, party.list_id).leader,
        role: `${partyProfile(board, party.list_id).name} · ${partyProfile(board, party.list_id).description}` };
    return { name: koreanText(board, name), role: '해당 질문의 응답 항목' };
};
export const groupSeatSummary = (board, poll, groupId) => {
    const values = (poll?.values || []).filter((row) => partyProfile(board, row.list_id).group === groupId);
    return { values, total: values.length ? values.reduce((sum, row) => sum + row.seats, 0) : null };
};
export const presetSeatSum = (board, poll, presetId) => {
    const preset = board.coalition_context?.presets?.find((row) => row.id === presetId);
    return preset ? selectedSeatSum(poll, preset.list_ids, board) : { status: 'held', total: null };
};
export const selectionRelationships = (board, selected) => {
    const ids = new Set(selected);
    return (board.coalition_context?.relationships || []).filter((row) => {
        if (row.kind === 'refusal') return ids.has(row.anchor) && row.targets.some((id) => ids.has(id));
        if (row.kind === 'external_support') return row.parties.some((id) => ids.has(id))
            && [...ids].some((id) => partyProfile(board, id).group === row.target_group);
        return row.parties.length > 1 && row.parties.every((id) => ids.has(id));
    });
};
