const DATA_ROOT = '/public/data';
let bundlePromise = null;

const loadJson = async (filename) => {
    const response = await fetch(`${DATA_ROOT}/${filename}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${filename} (${response.status})`);
    return response.json();
};

// Core political records.  This module intentionally owns only the initial
// manifest → board/calendar sequence, never country geometry.
export const loadElectionBundle = () => {
    if (!bundlePromise) {
        bundlePromise = (async () => {
            const manifest = await loadJson('elections_ui_manifest_v1.json');
            if (manifest?.claude_handoff_gate?.can_start_ui !== true) {
                throw new Error('선거 UI 매니페스트가 아직 열려 있지 않습니다.');
            }
            const [board, calendar] = await Promise.all([
                loadJson('elections_board_v1.json'),
                loadJson('elections_calendar_master_v1.json'),
            ]);
            // 대진 목차는 아직 없을 수 있다(수집 전). 없으면 null 이고, 그러면 일반
            // 브리핑이 붙는 일정이 하나도 없을 뿐 나머지 화면은 그대로 선다.
            const contests = await loadJson('elections_contests_index_v1.json').catch(() => null);
            const countries = new Map((board.countries || []).map((country) => [country.iso3, country]));
            // 중국 당 회의 일정은 보드 생성기 밖의 검토 파일이다. 보드가 이미
            // race_progress 를 싣고 오면 그쪽이 우선이고, 파일이 없으면 "선거 진행
            // 상황"이 예전처럼 수집 예정으로 남을 뿐이다.
            const china = countries.get('CHN');
            if (china && !china.race_progress) {
                const plenums = await loadJson('race_progress_chn_v1.json').catch(() => null);
                if (plenums?.schema === 'race_progress_v1' && plenums.iso3 === 'CHN') china.race_progress = plenums;
            }
            return { manifest, board, calendar, countries, contests };
        })();
    }
    return bundlePromise;
};
