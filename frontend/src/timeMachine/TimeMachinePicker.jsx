import { useEffect, useRef, useState } from 'react';
import { destinationTime, koreaDate } from './timeMachine.js';
import { datePartBounds, selectDatePart, SELECTABLE_FIRST_DATE } from './dateSelection.js';
import { prefersReducedMotion } from '../lib/format.js';
import s from './TimeMachine.module.css';

const PARTS = ['연', '월', '일'];
const UNITS = ['년', '월', '일'];
const point = (angle, radius) => ({ x: 410 - Math.cos(angle) * radius, y: 360 + Math.sin(angle) * radius });

export default function TimeMachinePicker({ asOf, onTravel }) {
  const today = koreaDate();
  const currentDate = koreaDate(asOf ? new Date(asOf) : new Date());
  const [date, setDate] = useState(currentDate < SELECTABLE_FIRST_DATE ? SELECTABLE_FIRST_DATE : currentDate);
  const [step, setStep] = useState(0);
  const [turn, setTurn] = useState(null);
  const [reduced] = useState(prefersReducedMotion);
  const [unlocked, setUnlocked] = useState(0);
  const [dayConfirmed, setDayConfirmed] = useState(false);
  const [error, setError] = useState('');
  const ruler = useRef(null);
  const wheel = useRef({ amount: 0, at: 0 });
  const parts = date.split('-').map(Number);
  const value = parts[step];
  const [min, max] = datePartBounds(date, step, today);
  const available = today >= SELECTABLE_FIRST_DATE;
  const turning = turn !== null;
  const changeStep = (next) => {
    if (turning || next === step) return;
    if (reduced) { setStep(next); return; }
    setTurn(next);
  };
  useEffect(() => {
    if (turn === null) return undefined;
    const finish = setTimeout(() => { setStep(turn); setTurn(null); }, 1200);
    return () => clearTimeout(finish);
  }, [turn]);
  const select = (next) => {
    setDate((previous) => selectDatePart(previous, step, next, today));
    setDayConfirmed(step === 2);
    setError('');
  };
  useEffect(() => {
    const node = ruler.current;
    wheel.current = { amount: 0, at: 0 };
    const onWheel = (event) => {
      event.preventDefault();
      if (turning) return;
      const now = performance.now();
      if (now - wheel.current.at > 180 || Math.sign(event.deltaY) !== Math.sign(wheel.current.amount)) wheel.current.amount = 0;
      wheel.current.amount += event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 300 : 1);
      wheel.current.at = now;
      if (Math.abs(wheel.current.amount) < 45) return;
      const direction = Math.sign(wheel.current.amount);
      wheel.current.amount = 0;
      setDate((previous) => {
        const current = Number(previous.split('-')[step]);
        return selectDatePart(previous, step, current + direction, today);
      });
      setError('');
      setDayConfirmed(step === 2);
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  }, [step, today, turning]);
  const travel = () => {
    if (!available || !dayConfirmed) return;
    const target = date >= SELECTABLE_FIRST_DATE && destinationTime(date, new Date(), asOf ? new Date(asOf) : new Date());
    if (!target) { setError('현재 보고 있는 날짜와 다른 날짜를 선택해 주세요.'); return; }
    onTravel(target);
  };
  const selectAndAdvance = (index, number) => {
    if (turning) return;
    const selectedDate = selectDatePart(date, index, number, today);
    setDate(selectedDate);
    setError('');
    setDayConfirmed(index === 2);
    changeStep(Math.min(2, index + 1));
    setUnlocked(Math.max(unlocked, Math.min(2, index + 1)));
  };
  return <div className={s.picker} role="region" aria-label="타임머신">
    <div className={s.machineContent}>
      <time className={s.currentDate} dateTime={date} aria-live="polite">{date.replaceAll('-', '. ')}</time>
      <button className={s.launch} type="button" onClick={travel} disabled={!available || !dayConfirmed || date === currentDate}>시간 이동</button>
      {error && <p role="alert">{error}</p>}
    </div>
    <div className={s.dateSelector}>
      <div className={s.steps} aria-label="날짜 선택 단계">
        {PARTS.map((part, index) => <button key={part} type="button" disabled={turning || index > unlocked}
          aria-current={step === index ? 'step' : undefined} onClick={() => { changeStep(index); setError(''); }}>
          <small>0{index + 1} · {part}</small><strong>{parts[index]}</strong>
        </button>)}
      </div>
      <div ref={ruler} className={s.ruler}>
        {(turning ? [step, turn] : [step]).map((pageIndex) => <div key={pageIndex}
          className={`${s.rulerPage} ${turning ? (pageIndex === step ? s.pageOut : s.pageIn) : ''}`}
          aria-hidden={turning && pageIndex === step ? true : undefined}>
        <svg viewBox="0 0 440 720" preserveAspectRatio="none" aria-hidden="true">
          <path className={s.referenceLine} d="M 10 360 H 432" />
          {[pageIndex].map((index) => {
            const part = PARTS[index];
            const radius = 350;
            const start = point(-1.35, radius);
            const end = point(1.35, radius);
            return <g key={part} className={s.activeRing}>
              <path className={s.rulerArc} d={`M ${start.x} ${start.y} A ${radius} ${radius} 0 0 0 ${end.x} ${end.y}`} />
              {Array.from({ length: 61 }, (_, tick) => {
                const angle = (tick - 30) * .045;
                const major = tick % 5 === 0;
                const from = point(angle, radius);
                const to = point(angle, radius - (major ? 18 : 7));
                return <line key={tick} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={major ? s.majorTick : s.minorTick} />;
              })}
              <path className={s.rulerPointer} d={`M ${410 - radius - 20} 360 h 28 m -28 0 l -6 -4 v 8 Z`} />
            </g>;
          })}
        </svg>
        {[pageIndex].map((index) => {
            const part = PARTS[index];
          const [lower, upper] = datePartBounds(date, index, today);
          return <div key={part} className={s.activeValues}>
            {Array.from({ length: 5 }, (_, tick) => {
              const offset = tick - 2;
              const number = parts[index] + offset;
              const pos = point(offset * .45, 350);
              return <button key={offset} type="button" className={`${s.rulerValue} ${offset === 0 ? s.selectedValue : ''}`}
                style={{ left: `${(pos.x + 24) / 440 * 100}%`, top: `${pos.y / 720 * 100}%` }}
                disabled={turning || !available || index > unlocked || number < lower || number > upper} aria-label={`${number}${UNITS[index]}`}
                aria-pressed={offset === 0} onClick={() => selectAndAdvance(index, number)}>{String(number).padStart(index === 0 ? 4 : 2, '0')}<span>{UNITS[index]}</span></button>;
            })}
          </div>;
        })}
        </div>)}
      </div>
      <div className={s.rulerControls}>
        <button type="button" aria-label={`${PARTS[step]} 감소`} disabled={turning || !available || value <= min} onClick={() => select(value - 1)}>−</button>
        <button type="button" aria-label={`${PARTS[step]} 증가`} disabled={turning || !available || value >= max} onClick={() => select(value + 1)}>+</button>
      </div>
    </div>
  </div>;
}
