import s from './SatelliteRelay.module.css';

/** Decorative relay: packet positions are projected by the existing globe render loop. */
export default function SatelliteRelay({ satelliteRef, signalRefs, departing = false }) {
  return <>
    <svg className={s.signals} aria-hidden="true">
      {[0, 1].map((index) => <g key={index} ref={(node) => { signalRefs.current[index] = node; }} visibility="hidden">
        <path className={s.trail} fill="none" />
        <circle className={s.origin} r="4" />
        <circle className={s.packetHalo} r="8" />
        <circle className={s.packet} r="2.5" />
      </g>)}
    </svg>
    <div ref={satelliteRef} className={`${s.relay} ${departing ? s.departing : ''}`}>
      <img className={s.craft} src="/satellite-relay.png" alt="" aria-hidden="true" draggable={false} width="1254" height="1254" />
    </div>
  </>;
}
