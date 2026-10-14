import { validateIsraelBoard } from './israel-analysis.js';

let pending = null;
let expires = 0;
export const loadIsraelElectionAnalysis = () => {
    if (!pending || Date.now() >= expires) {
        expires = Date.now() + 5 * 60 * 1000;
        pending = (async () => {
            const [boardResponse, statusResponse] = await Promise.all([
                fetch('/public/data/israel_election_analysis_v1.json', { cache: 'no-cache' }),
                fetch('/public/data/israel_election_analysis_status_v1.json', { cache: 'no-cache' }),
            ]);
            if (!boardResponse.ok || !statusResponse.ok) throw new Error('검토 자료 파일을 불러오지 못했습니다.');
            const [body, status] = await Promise.all([boardResponse.text(), statusResponse.json()]);
            const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
            const digest = [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
            if (digest !== status.board_sha256) throw new Error('이스라엘 자료와 상태 파일의 버전이 다릅니다.');
            const board = validateIsraelBoard(JSON.parse(body), status);
            return { board, status, error: null };
        })().catch((error) => {
            expires = Date.now() + 60 * 1000;
            return { board: null, status: null, error: error.message };
        });
    }
    return pending;
};
