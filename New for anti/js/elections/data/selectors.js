export const monthKeys = (calendar) => Object.keys(calendar?.world_by_month || []).sort();

export const initialMonth = (calendar) => {
    const current = new Date().toISOString().slice(0, 7);
    const months = monthKeys(calendar);
    return months.includes(current) ? current : months.find((month) => month >= current) || months.at(-1) || null;
};

export const eventsForMonth = (calendar, month) => calendar?.world_by_month?.[month] || [];

export const eventsByDate = (events) => {
    const groups = new Map();
    [...events].sort((a, b) => String(a.date || '').localeCompare(String(b.date || ''))).forEach((event) => {
        const key = event.date || '불명';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(event);
    });
    return [...groups.entries()];
};

export const countryEvents = (country) => (country?.events || []).filter((event) => event?.date !== '없음');

export const readableSpectrum = (spectrum) => ({
    conservative: '보수',
    nationalist_conservative: '국가주의·보수',
    progressive: '진보',
    centrist: '중도',
    catch_all_governing_party: '집권당 중심',
    authoritarian_personalist: '권위주의 체제',
    authoritarian_party_state: '당국가 체제',
    authoritarian_cpc: '공산당 일당 체제',
    theocratic_authoritarian: '신정 체제',
}[spectrum] || spectrum || '불명');

export const screenStatus = (manifest, iso3, screen) => manifest?.countries?.[iso3]?.screens?.[screen]?.status || 'disabled';
