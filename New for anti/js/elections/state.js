export const createElectionState = () => {
    let value = { mode: 'world', iso3: null, month: null };
    const listeners = new Set();

    return {
        get: () => value,
        set(next) {
            value = { ...value, ...next };
            listeners.forEach((listener) => listener(value));
        },
        subscribe(listener) {
            listeners.add(listener);
            return () => listeners.delete(listener);
        },
    };
};
