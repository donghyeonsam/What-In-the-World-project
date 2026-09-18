import { useId } from 'react';
import s from './SatelliteRelay.module.css';

/** Decorative relay: packet positions are projected by the existing globe render loop. */
export default function SatelliteRelay({ satelliteRef, signalRefs }) {
  const id = useId().replace(/:/g, '');
  return <>
    <svg className={s.signals} aria-hidden="true">
      {[0, 1].map((index) => <g key={index} ref={(node) => { signalRefs.current[index] = node; }} visibility="hidden">
        <path className={s.trail} fill="none" />
        <circle className={s.origin} r="4" />
        <circle className={s.packetHalo} r="8" />
        <circle className={s.packet} r="2.5" />
      </g>)}
    </svg>
    <div ref={satelliteRef} className={s.relay}>
      <div className={s.orbit} aria-hidden="true" />
      <svg className={s.craft} viewBox="0 0 240 180" aria-hidden="true">
        <defs>
          <linearGradient id={`${id}metal`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#eefaff" /><stop offset=".3" stopColor="#91aab8" />
            <stop offset=".55" stopColor="#344a60" /><stop offset=".8" stopColor="#152337" /><stop offset="1" stopColor="#668d9c" />
          </linearGradient>
          <linearGradient id={`${id}solar`} x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#276c8c" /><stop offset=".48" stopColor="#123951" /><stop offset="1" stopColor="#071c33" />
          </linearGradient>
          <radialGradient id={`${id}dish`} cx=".3" cy=".25" r=".8">
            <stop stopColor="#d4e9ed" /><stop offset=".5" stopColor="#7796a8" /><stop offset="1" stopColor="#263e51" />
          </radialGradient>
          <pattern id={`${id}cells`} width="12" height="13" patternUnits="userSpaceOnUse">
            <path d="M0 0H12V13H0Z" fill="none" stroke="#67c7e1" strokeWidth=".55" opacity=".55" />
            <path d="M6 1V12" stroke="#acd4dc" strokeWidth=".35" opacity=".3" />
          </pattern>
        </defs>
        <g transform="translate(122 87) rotate(-27)">
          <path d="M-94 2H97" stroke="#7c9fae" strokeWidth="5" />
          {[-103, 32].map((x) => <g key={x} transform={`translate(${x} -25) skewY(8)`}>
            <rect width="72" height="49" rx="1" fill={`url(#${id}solar)`} stroke="#8cb7c7" strokeWidth="1.3" />
            <rect width="72" height="49" fill={`url(#${id}cells)`} />
            <path d="M24 0V49M48 0V49M0 24.5H72" stroke="#b2cbd0" strokeWidth="1.2" opacity=".7" />
            <path d="M0 49L4 53H76L72 49" fill="#12273d" stroke="#41627b" strokeWidth=".6" />
          </g>)}
          <path d="M-22-22L0-34L26-19V26L4 38L-22 22Z" fill={`url(#${id}metal)`} stroke="#90b0bf" />
          <path d="M-22-22L4-8L26-19M4-8V38" fill="none" stroke="#b4cfda" strokeWidth="1.2" />
          <path d="M-15-14L-4-8V17L-15 12Z" fill="#b5a170" opacity=".8" />
          <path d="M10 4L22-2V18L10 24Z" fill="#0b1d30" stroke="#517d93" />
          <path d="M12 8L20 4M12 13L20 9M12 18L20 14" stroke="#70d9ef" strokeWidth="1.2" />
          <path d="M-5-24L-8-43" stroke="#a2bfcb" strokeWidth="4" />
          <ellipse cx="-8" cy="-45" rx="26" ry="17" transform="rotate(-15 -8 -45)" fill={`url(#${id}dish)`} stroke="#c8e1e7" strokeWidth="1.2" />
          <path d="M-31-42L-9-65L16-51M-9-65L-8-45" fill="none" stroke="#cadce4" strokeWidth="1" />
          <circle cx="-9" cy="-65" r="2.5" fill="#d5f7ff" />
          <path d="M4 38V55M-6 55H14" stroke="#698a9d" strokeWidth="1.5" />
          <circle cx="4" cy="55" r="2" fill="#78e6ff" />
        </g>
        <path d="M150 103L169 109L165 119L147 113Z" fill="#263f54" stroke="#78becf" />
        <ellipse cx="168" cy="114" rx="3" ry="6" transform="rotate(22 168 114)" fill="#b7f5ff" />
        <ellipse cx="169" cy="114" rx="8" ry="12" fill="#79e7ff" opacity=".12" />
      </svg>
    </div>
  </>;
}
