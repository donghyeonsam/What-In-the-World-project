export const FIRST_DATE = '2026-09-06';
export const TRAVEL_DURATION = 5200;
const KST = 9 * 60 * 60 * 1000;

export function koreaDate(now = new Date()) {
  return new Date(now.getTime() + KST).toISOString().slice(0, 10);
}

export function destinationTime(date, now = new Date(), current = now) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < FIRST_DATE || date > koreaDate(now) || date === koreaDate(current)) return null;
  const clock = new Date(now.getTime() + KST).toISOString().slice(11, 23);
  const target = new Date(`${date}T${clock}+09:00`);
  return Number.isFinite(target.getTime()) && koreaDate(target) === date ? target.toISOString() : null;
}

export function readAsOf(search, now = new Date()) {
  const value = new URLSearchParams(search).get('asOf');
  if (!value || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || date > now || koreaDate(date) < FIRST_DATE) return null;
  return date.toISOString();
}

export function timeLabel(value) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}

export function stageTimeLabel(value) {
  const date = new Date(new Date(value).getTime() + KST);
  return `${date.getUTCFullYear()}년 ${date.getUTCMonth() + 1}월 ${date.getUTCDate()}일 ${date.getUTCHours()}시 ${String(date.getUTCMinutes()).padStart(2, '0')}분`;
}
