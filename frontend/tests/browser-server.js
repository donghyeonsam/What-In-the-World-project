// Explicit contract fixtures for browser QA only. Never imported by the app.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../dist/', import.meta.url));
const article = (id, tone) => ({ articleId: id, articleTitle: `검증 기사 ${id}`, articleTone: tone, articlePublisher: '검증 매체', publishedAt: '2026-09-08T12:30:00' });
const articles = [article('1', 'POSITIVE'), article('2', 'NEUTRAL'), article('3', 'NEGATIVE')];
const themes = [{ themeId: 1, themeName: '반도체', fieldName: '산업', articleCount24: 50 }, { themeId: 2, themeName: '기후', fieldName: '환경', articleCount24: 20 }];
const tones = [{ country: { countryCode: 'KR', countryName: '한국', lat: 36.5, lng: 127.9 }, toneAvg: 75, toneMin: 40, toneMax: 90, toneSd: 12.5, articleCount: 40 }, { country: { countryCode: 'US', countryName: '미국', lat: 38.9, lng: -95.7 }, toneAvg: 20, toneMin: 5, toneMax: 60, toneSd: 20, articleCount: 35 }];
const analysisSummary = { analysisId: 7, countryCode: 'KR', title: '공급망 다변화와 국내 산업의 대응',
  summary: '검증용 분석: 국내 언론은 공급망 재편이 반도체 산업에 미치는 영향과 기업의 대응에 주목합니다.',
  articleCount: 15, windowEnd: '2026-09-18T09:00:00+09:00' };
const analysisDetail = { ...analysisSummary, issueId: 1, details: [
  '검증용 상세 1: 주요 기업의 생산 거점 다변화와 공급 안정성 확보를 다룹니다.',
  '검증용 상세 2: 정책 변화가 수출과 투자 계획에 미치는 영향을 설명합니다.',
  '검증용 상세 3: 단기 비용 부담과 장기 경쟁력 확보를 함께 검토합니다.',
] };
// Test-only sessions and account. Never forwards account requests to a real server.
const sessions = new Set();
const fixtureUser = { id: 999, email: 'preview@example.com', authProvider: 'LOCAL', role: 'USER' };
const port = Number(process.env.PORT || 5175);
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/v1')) {
    let data;
    let status = 200;
    const route = url.pathname.slice('/api/v1'.length);
    const analysisAvailable = !url.searchParams.has('asOf') || new Date(url.searchParams.get('asOf')) >= new Date(analysisSummary.windowEnd);
    const token = (req.headers.cookie || '').match(/(?:^|;\s*)fixture-session=([^;]+)/)?.[1];
    if (route === '/auth/login' && req.method === 'POST') {
      let input = ''; for await (const chunk of req) input += chunk;
      const credentials = JSON.parse(input || '{}');
      if (credentials.email === fixtureUser.email && credentials.password === 'preview1234') {
        const value = crypto.randomUUID(); sessions.add(value);
        res.setHeader('Set-Cookie', `fixture-session=${value}; Path=/; HttpOnly; SameSite=Lax`);
      } else status = 401;
    }
    else if (route === '/users/me') { if (sessions.has(token)) data = fixtureUser; else status = 401; }
    else if (route === '/auth/logout' && req.method === 'POST') { sessions.delete(token); res.setHeader('Set-Cookie', 'fixture-session=; Path=/; Max-Age=0'); }
    else if (route === '/articles/filters') data = { countries: [{ countryCode: 'KR', countryName: '대한민국' }, { countryCode: 'US', countryName: '미국' }], fields: themes.map((t, i) => ({ fieldId: i + 1, fieldName: t.fieldName, themes: [t] })) };
    else if (route === '/articles') data = { items: articles.map((a) => ({ ...a, countryCode: url.searchParams.get('countryCode') || 'KR', countryName: '대한민국', themeId: Number(url.searchParams.get('themeId') || 1), themeName: '반도체' })), page: 1, size: 12, totalElements: 3, totalPages: 1 };
    else if (route.startsWith('/articles/')) data = { ...articles[0], summary: '브라우저 검증용 기사 요약입니다.', url: 'https://example.com' };
    else if (route === '/global/issues') data = { totalArticleCount: 12345, recent24ArticleCount: 100, globalIssues: [{ issueId: 1, issueName: '반도체 공급망 변화', themeName: '반도체', fieldName: '산업', firstSeenAt: '2026-09-08T09:00:00', scoreVersion: 'hierarchical-v1', globalHeatScore: 82.5, countryCount: 7 }] };
    else if (route === '/themes/by-field') data = themes.map((item, index) => ({ fieldId: index + 1, fieldName: item.fieldName, themes: [item] }));
    else if (/^\/countries\/\w+\/themes\/popular$/.test(route)) data = { countryCode: 'KR', countryName: '한국', popularThemes: themes.map((item) => ({ ...item, themeTimeStamp: { interval: 60, timestamp: Array.from({ length: 24 }, (_, i) => ({ time: `2026-09-08T${String(i).padStart(2, '0')}:00:00`, articleCount: i % 5 })) } })) };
    else if (route === '/countries/KR') data = { countryCode: 'KR', countryName: '한국', todayArticleCount: 42, globalRank: 2, countryIssues: [{ issueId: 1, fieldName: '경제', themeName: '반도체', issueName: '반도체 공급망 변화', scoreVersion: 'hierarchical-v1', localHeatScore: 87.4 }], popularThemes: themes, sourceMentions: [{ countryCode: 'US', countryName: '미국', mentionRatio: .75 }], targetMentions: [{ countryCode: 'GB', countryName: '영국', mentionRatio: .6 }] };
    else if (route.startsWith('/countries/')) { status = 404; }
    else if (route === '/themes/1/overview') data = { themeId: 1, themeName: '반도체', themeDescription: '반도체 산업 동향', primaryIssues: [{ issueId: 1, issueTitle: '반도체 공급망 변화' }], representArticles: articles };
    else if (route === '/themes/2/overview') data = { themeId: 2, themeName: '기후', themeDescription: null, primaryIssues: [], representArticles: [] };
    else if (route === '/global/issues/1') data = { issueInfo: { issueId: 1, issueName: '반도체 공급망 변화', articleCount: 800, countryCount: 2 }, countryTones: tones };
    else if (route === '/global/issues/1/country-analyses') data = { issueId: 1, countryAnalyses: analysisAvailable ? [analysisSummary] : [] };
    else if (/^\/global\/issues\/1\/country-analyses\/[a-z]{2}$/i.test(route)) data = { analysis: analysisAvailable && route.split('/').at(-1).toUpperCase() === 'KR' ? analysisDetail : null };
    else if (route === '/issues/1/overview') data = { issuePreview: { issueTitle: '반도체 공급망 변화', themeTitle: '반도체', articleCount: 800 }, countryTones: tones, representArticles: articles };
    else status = 404;
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ status, message: status === 200 ? '성공' : '국가 데이터가 없습니다.', ...(data === undefined ? {} : { data }) }));
    return;
  }
  const filename = path.resolve(root, `.${url.pathname === '/' ? '/index.html' : url.pathname}`);
  if (!filename.startsWith(root)) { res.writeHead(403); res.end(); return; }
  try {
    const data = await readFile(filename);
    res.setHeader('Content-Type', ({ '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.jpg': 'image/jpeg' })[path.extname(filename)] || 'application/octet-stream');
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
}).listen(port, '127.0.0.1', () => console.log(`Contract-fixture browser server: http://127.0.0.1:${port}`));
