import { useState, useEffect } from "react";

/**
 * Persists a numeric "limit" preference in localStorage.
 * key: e.g. "viz.limit.eventlog"
 * options: allowed values (shown in a select or slider)
 */
export function useLimitPref(
  key: string,
  defaultValue: number,
  options: number[] = [50, 100, 200, 500]
): [number, (n: number) => void, number[]] {
  const [limit, setLimitState] = useState<number>(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored) {
        const n = parseInt(stored, 10);
        if (options.includes(n)) return n;
      }
    } catch {}
    return defaultValue;
  });

  function setLimit(n: number) {
    setLimitState(n);
    try { localStorage.setItem(key, String(n)); } catch {}
  }

  return [limit, setLimit, options];
}
