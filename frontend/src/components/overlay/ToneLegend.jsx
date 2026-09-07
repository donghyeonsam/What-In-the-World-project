import { useEffect, useRef } from 'react';
import s from './cosmos.module.css';

/**
 * 지구본 위 여론 톤 범례 — 지금 칠하고 있는 토픽 이름과 색 축, 표본 부족 표시를 함께 둔다.
 * 색만 칠하고 축을 안 주면 무슨 색이 무슨 뜻인지 알 수 없다.
 * 출처: What in the World.html #tone-legend
 *
 * @param {{topicName?: string|null, onClear?: () => void, minSample?: number}} props
 */
export default function ToneLegend({ topicName, onClear, minSample = 30 }) {
  if (!topicName) return null;
  return (
    <div className={s.legend} role="note" aria-label="토픽 여론 톤 범례">
      <div className={s.topic}>
        🗺 <span>{topicName}</span>
        {onClear && (
          <button type="button" title="여론 톤 끄기" aria-label="여론 톤 끄기" onClick={onClear}>
            ✕
          </button>
        )}
      </div>
      <div className={s.ramp} aria-hidden="true" />
      <div className={s.labels}>
        <span>비판</span>
        <span>중립</span>
        <span>우호</span>
      </div>
      <div className={s.none}>
        <i />
        표본 부족 · 기사 {minSample}건 미만
      </div>
    </div>
  );
}

/**
 * 별 배경 캔버스 — 리사이즈마다 다시 뿌린다.
 * 출처: What in the World.html #stars
 */
export function StarField() {
  const ref = useRef(null);

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv.getContext('2d');
    const draw = () => {
      cv.width = innerWidth;
      cv.height = innerHeight;
      const n = Math.min((innerWidth * innerHeight) / 4200, 420);
      for (let i = 0; i < n; i++) {
        const x = Math.random() * cv.width;
        const y = Math.random() * cv.height;
        const r = Math.random() * 1.15 + 0.15;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 7);
        ctx.fillStyle = `rgba(${(200 + Math.random() * 55) | 0},${(215 + Math.random() * 40) | 0},255,${
          0.12 + Math.random() * 0.5
        })`;
        ctx.fill();
      }
    };
    draw();
    addEventListener('resize', draw);
    return () => removeEventListener('resize', draw);
  }, []);

  return <canvas className={s.stars} ref={ref} aria-hidden="true" />;
}
