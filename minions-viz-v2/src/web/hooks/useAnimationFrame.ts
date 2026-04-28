import { useRef, useEffect, useCallback } from "react";

export function useAnimationFrame(callback: (dt: number) => void, active = true) {
  const rafRef = useRef<number>(0);
  const prevRef = useRef<number>(0);
  const cbRef = useRef(callback);
  cbRef.current = callback;

  const loop = useCallback((time: number) => {
    if (prevRef.current) {
      const dt = Math.min(time - prevRef.current, 50);
      cbRef.current(dt);
    }
    prevRef.current = time;
    rafRef.current = requestAnimationFrame(loop);
  }, []);

  useEffect(() => {
    if (!active) return;
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [active, loop]);
}
