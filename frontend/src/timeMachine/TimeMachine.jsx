import { useEffect, useRef, useState } from 'react';
import { TRAVEL_DURATION, koreaDate, stageTimeLabel } from './timeMachine.js';
import { prefersReducedMotion } from '../lib/format.js';
import s from './TimeMachine.module.css';

export { default as TimeMachinePicker } from './TimeMachinePicker.jsx';

export function useTimeTravel(trip, onArrive) {
  const [progress, setProgress] = useState(0);
  const [reduced] = useState(prefersReducedMotion);
  const complete = useRef(onArrive);
  complete.current = onArrive;
  const duration = reduced ? 700 : TRAVEL_DURATION;
  useEffect(() => {
    if (!trip) return undefined;
    setProgress(0);
    const started = performance.now();
    let frame;
    let done = false;
    const finish = () => { if (!done) { done = true; complete.current(); } };
    const tick = (now) => {
      const value = Math.min(1, (now - started) / duration);
      setProgress(value);
      if (value < 1) frame = requestAnimationFrame(tick);
      else finish();
    };
    frame = requestAnimationFrame(tick);
    const timer = setTimeout(finish, duration + 100);
    return () => { done = true; cancelAnimationFrame(frame); clearTimeout(timer); };
  }, [trip, duration]);
  if (!trip) return { progress: 0, reduced, date: null };
  const target = trip.target ? new Date(trip.target).getTime() : trip.departed;
  const start = trip.origin ? new Date(trip.origin).getTime() : trip.departed;
  const eased = 1 - Math.pow(1 - progress, 3);
  const date = new Date(start + (target - start) * eased);
  return { progress, reduced, date };
}

export function StageClock({ asOf, travelDate, centered = false }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (asOf) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [asOf]);
  const date = travelDate || asOf || now;
  return <div className={`${s.stageClock} ${centered ? s.centeredClock : ''}`}>
    <time dateTime={new Date(date).toISOString()}>{stageTimeLabel(date)}</time>
  </div>;
}

export function TimeTravelEffects({ trip, progress, reduced, onArrive }) {
  return <div className={s.travel} aria-label="시간 이동 중">
    {!reduced && <div className={s.orbitStage} aria-hidden="true" style={{
      '--warp-opacity': .25 + .65 * Math.sin(Math.PI * progress),
    }}>
      <div className={s.speedLines}>{Array.from({ length: 64 }, (_, index) => <i key={index} style={{
        '--angle': `${index * 137.5}deg`, '--delay': `${-index * .073}s`,
        '--distance': `${65 + (index * 47) % 220}px`,
        '--streak-speed': `${.38 + (index * .071) % .55}s`,
        '--start': `${100 + (index * 31) % 150}px`,
        '--drift': `${Math.sin(index * 2.1) * 13}deg`,
        '--origin-x': `${47 + (index * 7) % 7}%`,
        '--origin-y': `${46 + (index * 11) % 9}%`,
      }} />)}</div>
    </div>}
    <p role="status">{trip.target ? `${koreaDate(new Date(trip.target)).replaceAll('-', '. ')} 날짜로 이동 중` : '현재로 돌아오는 중'}</p>
    <button onClick={onArrive}>건너뛰기</button>
  </div>;
}
