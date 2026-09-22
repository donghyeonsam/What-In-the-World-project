import test from 'node:test';
import assert from 'node:assert/strict';
import { countryMetadata, iso3 } from '../src/data/countries.js';

const global47Codes = [
  'AE', 'AR', 'AT', 'AU', 'BD', 'BE', 'BR', 'CA', 'CH', 'CL', 'CO', 'CZ',
  'DE', 'DK', 'ES', 'FI', 'FR', 'GB', 'HK', 'ID', 'IE', 'IL', 'IN', 'IQ',
  'IR', 'IT', 'JP', 'KR', 'KZ', 'MX', 'MY', 'NL', 'PE', 'PH', 'PK', 'PL',
  'PT', 'RO', 'RU', 'SA', 'SE', 'SG', 'TH', 'TR', 'US', 'VN', 'ZA',
];

test('country metadata matches the collector global47 profile', () => {
  assert.equal(countryMetadata.length, 47);
  assert.deepEqual(countryMetadata.map(({ code }) => code).sort(), global47Codes);
  assert.equal(new Set(countryMetadata.map(({ id }) => id)).size, 47);
  assert.ok(countryMetadata.every(({ code, name, lat, lon, iso, flag, flagClass }) => (
    /^[A-Z]{2}$/.test(code)
    && name
    && Number.isFinite(lat)
    && Number.isFinite(lon)
    && /^[A-Z]{3}$/.test(iso)
    && flag
    && flagClass === `fi fi-${code.toLowerCase()}`
  )));
});

test('every supported country has a matching globe ISO mapping', () => {
  assert.equal(Object.keys(iso3).length, 47);
  for (const country of countryMetadata) {
    assert.deepEqual(iso3[country.id], [country.iso]);
  }
});
