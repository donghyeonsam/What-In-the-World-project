import { flagOf } from './responseAdapters.js';

// Geographic metadata only. Analytics are never filled with sample values.
export const countryMetadata = [
  ['KR', '한국', 36.5, 127.9, 'KOR'], ['US', '미국', 38.9, -95.7, 'USA'],
  ['GB', '영국', 54, -2.5, 'GBR'], ['AU', '호주', -25.3, 133.8, 'AUS'],
  ['AE', '아랍에미리트', 24.5, 53.6, 'ARE'], ['QA', '카타르', 25.3, 51.2, 'QAT'],
  ['ZA', '남아프리카공화국', -30.6, 22.9, 'ZAF'], ['KE', '케냐', .02, 37.9, 'KEN'],
  ['BR', '브라질', -10.3, -53.2, 'BRA'],
].map(([code, name, lat, lon, iso]) => ({ id: code.toLowerCase(), code, name, lat, lon, iso, flag: flagOf(code) }));
export const iso3 = Object.fromEntries(countryMetadata.map((country) => [country.id, [country.iso]]));
