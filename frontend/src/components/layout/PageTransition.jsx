import { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from '../../lib/format.js';
import s from './PageTransition.module.css';

// 뉴스 ↔ 대시보드 경계만 전환한다. 뉴스 필터/페이지 변경은 즉시 반영한다.
export default function PageTransition({ screenKey, children }) {
  const [displayedKey, setDisplayedKey] = useState(screenKey);
  const previousScreen = useRef(children);
  const reduced = prefersReducedMotion();
  const leaving = !reduced && screenKey !== displayedKey;

  useEffect(() => {
    if (!leaving) previousScreen.current = children;
  }, [children, leaving]);

  useEffect(() => {
    if (screenKey === displayedKey) return undefined;
    if (reduced) {
      setDisplayedKey(screenKey);
      return undefined;
    }
    const timer = setTimeout(() => setDisplayedKey(screenKey), 120);
    return () => clearTimeout(timer);
  }, [screenKey, displayedKey, reduced]);

  return <div key={reduced ? screenKey : displayedKey}
    className={`${s.screen} ${leaving ? s.leaving : s.entering}`}
    {...(leaving ? { inert: '' } : {})}>
    {leaving ? previousScreen.current : children}
  </div>;
}
