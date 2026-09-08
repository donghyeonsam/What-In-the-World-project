// Explicit contract fixtures for browser QA only. Never imported by the app.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../dist/', import.meta.url));
const article = (id, tone) => ({ articleId: id, articleTitle: `검증 기사 ${id}`, articleTone: tone, articlePublisher: '검증 매체', publishedAt: '2026-09-08T12:30:00' });
const articles = [article('1', 'POSITIVE'), article('2', 'NEUTRAL'), article('3', 'NEGATIVE')];
const themes = [{ themeId: 1, themeName: '반도체', fieldName: '산업', articleCount24: 50 }, { themeId: 2, themeName: '기후', fieldName: '환경', articleCount24: 20 }];
const tones = [{ country: { countryCode: 'KR', countryName: '한국', lat: 36.5, lng: 127.9 }, toneAvg: 75, toneMin: 40, toneMax: 90 }, { country: { countryCode: 'US', countryName: '미국', lat: 38.9, lng: -95.7 }, toneAvg: 20, toneMin: 5, toneMax: 60 }];
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/v1')) {
    let data;
    let status = 200;
    const route = url.pathname.slice('/api/v1'.length);
    if (route === '/global/issues') data = { totalArticleCount: 12345, recent24ArticleCount: 100, globalIssues: [{ issueId: 1, issueName: '반도체 공급망 변화', themeName: '반도체', fieldName: '산업', articleCount: 80, firstSeenAt: '2026-09-08T09:00:00' }] };
    else if (route === '/themes/by-field') data = themes.map((item, index) => ({ fieldId: index + 1, fieldName: item.fieldName, themes: [item] }));
    else if (/^\/countries\/\w+\/themes\/popular$/.test(route)) data = { countryCode: 'KR', countryName: '한국', popularThemes: themes.map((item) => ({ ...item, themeTimeStamp: { interval: 60, timestamp: Array.from({ length: 24 }, (_, i) => ({ time: `2026-09-08T${String(i).padStart(2, '0')}:00:00`, articleCount: i % 5 })) } })) };
    else if (route === '/countries/KR') data = { countryCode: 'KR', countryName: '한국', todayArticleCount: 42, globalRank: 2, popularThemes: themes, sourceMentions: [{ countryCode: 'US', countryName: '미국', mentionRatio: .75 }], targetMentions: [{ countryCode: 'GB', countryName: '영국', mentionRatio: .6 }], representArticles: articles };
    else if (route.startsWith('/countries/')) { status = 404; }
    else if (route === '/themes/1/overview') data = { themeId: 1, themeName: '반도체', themeDescription: '반도체 산업 동향', primaryIssues: [{ issueId: 1, issueTitle: '반도체 공급망 변화' }], representArticles: articles };
    else if (route === '/themes/2/overview') data = { themeId: 2, themeName: '기후', themeDescription: null, primaryIssues: [], representArticles: [] };
    else if (route === '/global/issues/1') data = { issueInfo: { issueId: 1, issueName: '반도체 공급망 변화', articleCount: 800, countryCount: 2 }, countryTones: tones };
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
}).listen(5175, '127.0.0.1', () => console.log('Contract-fixture browser server: http://127.0.0.1:5175'));
