// 슈퍼팩 화면의 "느림·먹통" 수정을 고정하는 테스트.
//   - 실패한 읽기는 캐시되지 않는다 (나갔다 들어오면 재시도)
//   - 늦게 도착한 도형이 지도를 덮어쓰지 못한다 (stale 가드)
//   - 도형이 아직 안 왔거나 못 받은 것을 "지도 미대응"으로 단정하지 않는다
import test from 'node:test';
import assert from 'node:assert/strict';

// ---- fetch 모의: 호출을 세고, 경로별로 실패/404/성공을 정한다 ---------------------------------------
const calls = [];
const plan = new Map();          // 경로 → (횟수) => 'ok' | 'fail' | 404
const bodies = new Map();        // 경로 → 응답 JSON
globalThis.fetch = async (url) => {
    const path = String(url).replace('/public/data/', '');
    calls.push(path);
    const n = calls.filter((c) => c === path).length;
    const mode = (plan.get(path) || (() => 'ok'))(n);
    if (mode === 'fail') throw new TypeError('network down');
    if (mode === 404) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => bodies.get(path) ?? {} };
};
const count = (path) => calls.filter((c) => c === path).length;

const geo = await import('../data/geo-service.js');
const fin = await import('../data/finance-service.js');
const { renderUsaDistrictMap } = await import('../country-explorer/usa-district-map.js');
const sp = await import('../country-explorer/special/usa-state-superpac.js');

test('geo: 실패한 도형 읽기는 캐시되지 않고 다음 호출이 다시 시도한다', async () => {
    plan.set('congressional_districts/USA/T1.json', (n) => (n === 1 ? 'fail' : 'ok'));
    bodies.set('congressional_districts/USA/T1.json', { features: [{ properties: { district: '01' } }] });
    await assert.rejects(geo.loadCongressionalDistricts('T1'));
    const again = await geo.loadCongressionalDistricts('T1');          // 예전에는 같은 거절이 영구히 돌아왔다
    assert.equal(again.features.length, 1);
    await geo.loadCongressionalDistricts('T1');
    assert.equal(count('congressional_districts/USA/T1.json'), 2, '성공한 뒤에는 캐시를 쓴다');
});

test('geo: 404 는 "도형 없음(null)"으로 기억하고 다시 요청하지 않는다', async () => {
    plan.set('congressional_districts/USA/T2.json', () => 404);
    assert.equal(await geo.loadCongressionalDistricts('T2'), null);
    assert.equal(await geo.loadCongressionalDistricts('T2'), null);
    assert.equal(count('congressional_districts/USA/T2.json'), 1);
});

test('geo: 국가 경계(admin1)도 실패를 캐시하지 않는다', async () => {
    plan.set('admin1/TST.json', (n) => (n === 1 ? 'fail' : 'ok'));
    bodies.set('admin1/TST.json', { features: [] });
    await assert.rejects(geo.loadAdmin1('TST'));
    assert.deepEqual(await geo.loadAdmin1('TST'), { features: [] });
});

const financeFixture = () => {
    bodies.set('usa_election_finance_index_v1.json', { cycles: { 2026: { national_file: 'nat.json' } }, display_contract: { federal_superpac_categories: ['super_pac'] } });
    // 전국 파일은 한 번 읽으면 캐시되므로, 이후 테스트가 쓸 주(YY)까지 처음부터 담아 둔다.
    bodies.set('nat.json', { states: { ZZ: { data_file: 'zz-index.json' }, YY: { data_file: 'yy-index.json' } } });
    bodies.set('zz-index.json', { races: [{ data_file: 'r1.json' }, { data_file: 'r2.json' }, { data_file: 'r3.json' }] });
    bodies.set('yy-index.json', { races: [{ data_file: 'r1.json' }] });
    ['r1', 'r2', 'r3'].forEach((id) => bodies.set(`${id}.json`, { race_id: id }));
};

test('finance: 레이스 파일 일부가 실패하면 실패 개수를 알리고, 재시도는 실패한 것만 다시 받는다', async () => {
    financeFixture();
    plan.set('r2.json', (n) => (n === 1 ? 'fail' : 'ok'));
    const first = await fin.loadStateFinance('ZZ');
    assert.equal(first.failed, 1);
    assert.deepEqual(first.races.map((r) => r.race_id), ['r1', 'r3']);
    const second = await fin.loadStateFinance('ZZ');
    assert.equal(second.failed, 0);
    assert.deepEqual(second.races.map((r) => r.race_id).sort(), ['r1', 'r2', 'r3']);
    assert.equal(count('r1.json'), 1, '이미 받은 파일은 다시 받지 않는다');
    assert.equal(count('r2.json'), 2);
});

test('finance: 주 인덱스 읽기가 실패하면 indexFailed 로 보고하고(null 아님), 다음 호출에서 복구된다', async () => {
    financeFixture();
    plan.set('yy-index.json', (n) => (n === 1 ? 'fail' : 'ok'));
    const first = await fin.loadStateFinance('YY');
    assert.equal(first?.indexFailed, true, '실패는 "자료 없음(null)"과 구분된다');
    const second = await fin.loadStateFinance('YY');         // 예전에는 null 이 세션 내내 굳었다
    assert.equal(second?.failed, 0);
    assert.equal(second.races.length, 1);
});

test('finance: 자료가 아예 없는 주는 null (실패와 다르다)', async () => {
    financeFixture();
    assert.equal(await fin.loadStateFinance('NOPE'), null);
});

// ---- 선거구 지도: stale 가드 ---------------------------------------------------------------------
const fakeHost = () => {
    const sets = [];
    return { sets, layers: { GeoJsonLayer: class { constructor(p) { Object.assign(this, p); } } },
        worldBaseLayers: ({ id }) => [{ id }], setElectionMap: (...args) => sets.push(args) };
};

test('지도: 도형을 기다리는 사이 사용자가 나갔다면 지도를 건드리지 않는다 (클릭 핸들러를 null 로 만들지 않는다)', async () => {
    bodies.set('congressional_districts/USA/T3.json', { features: [{ properties: { district: '01' }, geometry: { coordinates: [[[0, 0], [1, 1]]] } }] });
    const host = fakeHost();
    let stale = false;
    const pending = renderUsaDistrictMap({ host, stateId: 'T3', isStale: () => stale });
    stale = true;                                                      // 도형이 오기 전에 나갔다
    assert.equal(await pending, null);
    assert.equal(host.sets.length, 0, '늦게 온 도형이 지도를 덮어쓰면 안 된다');
});

test('지도: 사용자가 그대로면 그린다', async () => {
    const host = fakeHost();
    const drawn = await renderUsaDistrictMap({ host, stateId: 'T3', isStale: () => false });
    assert.equal(drawn, true);
    assert.equal(host.sets.length, 1);
});

test('지도: 도형 읽기가 실패해도 예외로 화면을 멈추지 않는다 (false)', async () => {
    plan.set('congressional_districts/USA/T4.json', () => 'fail');
    const host = fakeHost();
    assert.equal(await renderUsaDistrictMap({ host, stateId: 'T4' }), false);
    assert.equal(host.sets.length, 0);
});

test('지도: 이미 받은 geo 를 넘기면 다시 읽지 않는다', async () => {
    const host = fakeHost();
    const before = calls.length;
    const drawn = await renderUsaDistrictMap({ host, stateId: 'T5', geo: { features: [] } });
    assert.equal(drawn, true);
    assert.equal(calls.length, before, 'fetch 가 나가면 안 된다');
});

// ---- 하원 구획: 도형 상태 세 가지 --------------------------------------------------------------
const house = [{ race_id: 'USA:OH:house:01', office: 'house', district: '01', candidates: [] },
               { race_id: 'USA:OH:house:02', office: 'house', district: '02', candidates: [] }];
const render = (mapped) => sp.usaStateSuperPacHouse({ id: 'OH' }, house, mapped);

test('하원: 도형을 아직 기다리는 중이면 "지도 미대응"이라 단정하지 않는다', () => {
    const html = render(sp.MAPPING_PENDING);
    assert.doesNotMatch(html, /지도 미대응/);
    assert.doesNotMatch(html, /is-unmapped/);
    assert.doesNotMatch(html, /data-spac-district=/, '강조할 지도가 아직 없다');
    assert.match(html, /불러오는 중/);
});

test('하원: 도형을 받다가 실패했으면 "못 불러왔다"고 말하고, 미대응으로 칠하지 않는다', () => {
    const html = render(sp.MAPPING_FAILED);
    assert.doesNotMatch(html, /is-unmapped/);
    assert.match(html, /불러오지 못했습니다/);
    assert.ok(html.indexOf('불러오지 못했습니다') < html.indexOf('elections-spac-district-list'), '안내는 목록 위에');
});

test('하원: 도형 읽기를 마쳤는데 선거구가 없으면 그때만 "지도 미대응"', () => {
    const html = render(new Set(['01']));
    assert.equal((html.match(/is-unmapped/g) || []).length, 1);
    assert.match(html, /data-spac-district="01"/);
    assert.doesNotMatch(html, /data-spac-district="02"/);
    assert.match(render(null), /지도 미대응/);                          // 도형 파일 자체가 없는 주
});
