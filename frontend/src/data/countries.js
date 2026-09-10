import { flagOf } from './responseAdapters.js';

// Geographic metadata only. Analytics are never filled with sample values.
export const countryMetadata = [
  ['US', '미국', 38.0, -97.0, 'USA'],
  ['KR', '대한민국', 36.5, 127.8, 'KOR'],
  ['JP', '일본', 36.2, 138.3, 'JPN'],
  ['DE', '독일', 51.2, 10.4, 'DEU'],
  ['GB', '영국', 54.0, -2.0, 'GBR'],
].map(([code, name, lat, lon, iso]) => ({
  id: code.toLowerCase(), code, name, lat, lon, iso,
  flag: flagOf(code), flagImage: `/flags/${code.toLowerCase()}.svg`,
}));
export const iso3 = Object.fromEntries(countryMetadata.map((country) => [country.id, [country.iso]]));
