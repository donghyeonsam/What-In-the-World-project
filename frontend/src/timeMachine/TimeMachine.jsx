import { useEffect, useRef, useState } from 'react';
import { FIRST_DATE, TRAVEL_DURATION, destinationTime, koreaDate, timeLabel, stageTimeLabel } from './timeMachine.js';
import { prefersReducedMotion } from '../lib/format.js';
import s from './TimeMachine.module.css';

export function TimeMachinePicker({ asOf, onClose, onTravel }) {
  const dialog = useRef(null);
  const currentDate = koreaDate(asOf ? new Date(asOf) : new Date());
  const [date, setDate] = useState(currentDate);
  const [error, setError] = useState('');
  useEffect(() => {
    const opener = document.activeElement;
    const node = dialog.current;
    node.showModal();
    return () => { node.close(); opener?.focus(); };
  }, []);
  const submit = (event) => {
    event.preventDefault();
    const target = destinationTime(date, new Date(), asOf ? new Date(asOf) : new Date());
    if (!target) { setError(date === currentDate ? '현재 보고 있는 날짜로는 이동할 수 없습니다.' : '2026년 9월 6일부터 오늘까지 선택해 주세요.'); return; }
    onTravel(target);
  };
  const isCurrentDate = date === currentDate;
  return <dialog ref={dialog} className={s.picker} aria-labelledby="time-machine-title" onCancel={onClose}>
    <div className={`${s.machineDoor} ${s.doorLeft}`} data-time-machine-door="left" aria-hidden="true"><i /></div>
    <div className={`${s.machineDoor} ${s.doorRight}`} data-time-machine-door="right" aria-hidden="true"><i /></div>
    <div className={s.machineContent}>
      <button className={s.close} onClick={onClose} aria-label="타임머신 닫기" />
      <div className={s.pickerHead}>
        <h1 id="time-machine-title">TIME MACHINE</h1>
      </div>
      <div className={s.dial} aria-hidden="true">
        <i className={s.dialOuter} /><i className={s.dialInner} /><i className={s.dialCore} />
        <span>09·06</span><b>—</b><span>TODAY</span>
      </div>
      <form onSubmit={submit}>
        <label className={s.dateLabel} htmlFor="travel-date">DESTINATION</label>
        <input id="travel-date" className={s.dateInput} type="date" min={FIRST_DATE} max={koreaDate()} value={date} required onChange={(e) => { setDate(e.target.value); setError(''); }} />
        {error && <p role="alert">{error}</p>}
        <button className={s.launch} type="submit" disabled={isCurrentDate}><span>{isCurrentDate ? '다른 날짜를 선택하세요' : '시간 이동 시작'}</span><i aria-hidden="true" /></button>
      </form>
    </div>
  </dialog>;
}

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

export function StageClock({ asOf, travelDate }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (asOf) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [asOf]);
  const date = travelDate || asOf || now;
  return <div className={`${s.stageClock} ${travelDate ? s.rewindingClock : ''}`}>
    <time dateTime={new Date(date).toISOString()}>{stageTimeLabel(date)}</time>
  </div>;
}

export function TimeTravelEffects({ trip, progress, reduced, onArrive }) {
  const phase = progress < .18 ? '시간 좌표를 맞추는 중' : progress < .78 ? (trip.target ? '세계의 시간을 되감는 중' : '현재의 세계로 돌아가는 중') : (trip.target ? '그날의 세계에 도착합니다' : '지금의 세계에 도착합니다');
  return <div className={`${s.travel} ${reduced ? s.reduced : ''}`} aria-label="시간 이동 중">
    <div className={s.grain} />
    <div className={s.orbitStage} aria-hidden="true">
      <div className={s.halo} /><div className={s.orbit} /><div className={s.orbitTwo} /><div className={s.ticks} />
      <div className={s.scan} />
      {Array.from({ length: 28 }, (_, i) => <i key={i} className={s.streak} style={{ '--angle': `${i * 137.5}deg`, '--delay': `${-(i % 9) * .13}s`, '--length': `${40 + i % 5 * 18}px` }} />)}
    </div>
    <div className={s.readout}>
      <p className={s.eyebrow}>{trip.target ? 'BACK TO THE WORLD OF' : 'WELCOME BACK TO'}</p>
      <p className={s.phase} role="status">{reduced ? '선택한 시점으로 이동합니다' : phase}</p>
      <div className={s.track}><span style={{ transform: `scaleX(${progress})` }} /></div>
      <div className={s.coordinates}><span>DESTINATION · {trip.target ? timeLabel(trip.target) : '현재'}</span><span>{String(Math.round(progress * 100)).padStart(3, '0')}%</span></div>
    </div>
    <div className={s.travelFoot}><button onClick={onArrive}>연출 건너뛰기 ↗</button></div>
  </div>;
}
