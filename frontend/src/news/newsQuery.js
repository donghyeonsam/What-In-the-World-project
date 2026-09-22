export const PAGE_SIZE = 12;
const dateValue = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '';
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : '';
};
export function readNewsQuery(search) {
  const params = new URLSearchParams(search);
  const page = Number(params.get('page') || 1);
  return {
    countryCode: (params.get('countryCode') || '').toUpperCase(),
    fieldId: params.get('fieldId') || '', themeId: params.get('themeId') || '',
    from: dateValue(params.get('from')), to: dateValue(params.get('to')),
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  };
}
export function newsSearch(query) {
  const params = new URLSearchParams({ view: 'news' });
  for (const key of ['countryCode', 'fieldId', 'themeId', 'from', 'to']) {
    if (query[key]) params.set(key, query[key]);
  }
  params.set('page', String(query.page || 1));
  return `?${params}`;
}
export function queryError(query, filters) {
  if (query.from && query.to && query.from > query.to) return '시작일은 종료일보다 늦을 수 없습니다.';
  if (!filters) return '';
  if (query.countryCode && !filters.countries.some((c) => c.countryCode === query.countryCode)) return '지원하지 않는 국가입니다. 필터를 다시 선택해 주세요.';
  const field = filters.fields.find((f) => String(f.fieldId) === query.fieldId);
  if (query.fieldId && !field) return '지원하지 않는 분야입니다. 필터를 다시 선택해 주세요.';
  if (query.themeId && !(field ? [field] : filters.fields).some((f) => f.themes.some((t) => String(t.themeId) === query.themeId))) return '선택한 분야와 테마가 맞지 않습니다. 필터를 다시 선택해 주세요.';
  return '';
}
