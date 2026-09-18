import { useEffect, useState } from 'react';

export function remainingSeconds(deadline, now = Date.now()) {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

export function useVerificationTimer() {
  const [deadline, setDeadline] = useState(null);
  const [now, setNow] = useState(Date.now);
  const remaining = deadline === null ? 0 : remainingSeconds(deadline, now);
  useEffect(() => {
    if (deadline === null) return;
    const update = () => setNow(Date.now());
    update();
    const interval = setInterval(update, 1000);
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [deadline]);
  return {
    expired: deadline !== null && remaining === 0,
    label: `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`,
    start: (seconds = 300, requestedAt = Date.now()) => {
      setNow(Date.now());
      setDeadline(requestedAt + (Number.isFinite(seconds) && seconds > 0 ? seconds : 300) * 1000);
    },
    clear: () => setDeadline(null),
  };
}
