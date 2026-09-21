export const SELECTABLE_FIRST_DATE = '2026-09-19';

export function datePartBounds(date, step, today) {
  const [year, month] = date.split('-').map(Number);
  const [firstYear, firstMonth, firstDay] = SELECTABLE_FIRST_DATE.split('-').map(Number);
  const [lastYear, lastMonth, lastDay] = today.split('-').map(Number);
  if (step === 0) return [firstYear, lastYear];
  if (step === 1) return [year === firstYear ? firstMonth : 1, year === lastYear ? lastMonth : 12];
  return [year === firstYear && month === firstMonth ? firstDay : 1,
    year === lastYear && month === lastMonth ? lastDay : new Date(year, month, 0).getDate()];
}

export function selectDatePart(date, step, value, today) {
  const [min, max] = datePartBounds(date, step, today);
  if (value < min || value > max) return date;
  const parts = date.split('-').map(Number);
  parts[step] = value;
  parts[2] = Math.min(parts[2], new Date(parts[0], parts[1], 0).getDate());
  const next = parts.map((part, index) => String(part).padStart(index === 0 ? 4 : 2, '0')).join('-');
  return next < SELECTABLE_FIRST_DATE ? SELECTABLE_FIRST_DATE : next > today ? today : next;
}
