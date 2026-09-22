export const STORAGE_KEY = 'witw-personal-interests-v2';
export const emptyInterests = () => ({ countries: [], themes: [], issues: [] });
export const accountStorageKey = (id) => `${STORAGE_KEY}:${id}`;
export function parseInterests(value) {
  try {
    const parsed = JSON.parse(value);
    const clean = (items, country = false) => Array.isArray(items) ? items
      .filter((item) => item && (country ? /^[A-Z]{2}$/.test(item.id) : Number.isSafeInteger(item.id) && item.id > 0) && typeof item.name === 'string')
      .filter((item, index, all) => all.findIndex((other) => other.id === item.id) === index).slice(0, country ? 5 : 10) : [];
    return { countries: clean(parsed?.countries, true), themes: clean(parsed?.themes), issues: clean(parsed?.issues) };
  } catch { return emptyInterests(); }
}

// Countries narrow the publisher country; themes/issues are alternatives.
export async function loadPersonalNews(interests, source, api, signal, size = 12) {
  const countries = interests.countries.length ? interests.countries : [{ id: undefined, name: '전체 국가' }];
  const topics = [...interests.themes.map((item) => ({ ...item, kind: 'theme' })), ...interests.issues.map((item) => ({ ...item, kind: 'issue' }))];
  if (!topics.length && interests.countries.length) topics.push({ kind: 'country', name: '전체 테마' });
  const jobs = topics.flatMap((topic) => countries.map((country) => ({ topic, country })));
  const articles = new Map();
  const failed = [];
  let hasMore = false;
  for (let start = 0; start < jobs.length; start += 4) {
    signal?.throwIfAborted();
    const batch = jobs.slice(start, start + 4);
    const results = await Promise.allSettled(batch.map(({ topic, country }) => topic.kind === 'issue'
      ? api.overview(topic.id, country.id, signal).then((data) => ({ items: data.representArticles || [] }))
      : source.list({ countryCode: country.id, themeId: topic.kind === 'theme' ? topic.id : undefined, page: 1, size }, { signal })));
    results.forEach((result, index) => {
      const { topic, country } = batch[index];
      const label = `${country.id ? `${country.name} · ` : ''}${topic.name}`;
      if (result.status === 'rejected') { failed.push(label); return; }
      hasMore ||= result.value.totalElements > size;
      for (const article of result.value.items || []) {
        if (!article.articleId) continue;
        const key = String(article.articleId);
        const existing = articles.get(key);
        if (existing) existing.matches = [...new Set([...existing.matches, label])];
        else articles.set(key, { ...article, matches: [label] });
      }
    });
  }
  signal?.throwIfAborted();
  const time = (value) => Date.parse(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value || '') ? value : `${value}+09:00`) || 0;
  return { articles: [...articles.values()].sort((a, b) => time(b.publishedAt) - time(a.publishedAt)), failed, hasMore };
}
