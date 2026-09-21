// Explicit contract fixtures for browser QA only. Never imported by the app.
import http from 'node:http';
import { randomUUID } from 'node:crypto';
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
const interests = new Map(themes.map((theme) => [theme.themeId, { notificationEnabled: true }]));
let notificationsEnabled = true;
const seoulDateTime = (timestamp = Date.now()) => new Date(timestamp + 9 * 60 * 60 * 1000).toISOString().slice(0, 19);
const notification = (id, theme, articleCount, createdAt, readAt = null, userId = fixtureUser.id) => ({
  id, userId, title: `[${theme.themeName}]에 새로운 기사가 올라왔습니다.`,
  message: `새로운 기사 ${articleCount}건을 확인해보세요.`,
  fieldId: theme.themeId, fieldName: theme.fieldName, themeId: theme.themeId, themeName: theme.themeName,
  articleCount, createdAt, readAt, deletedAt: null,
});
const notifications = Array.from({ length: 24 }, (_, index) => notification(
  24 - index, themes[index % themes.length], 5 + (index * 7) % 37,
  seoulDateTime(Date.now() - (index * 2 + 1) * 60 * 60 * 1000),
  index < 8 ? null : seoulDateTime(Date.now() - index * 60 * 60 * 1000),
));
// The foreign record checks ownership without exposing it in this user's list.
notifications.push(notification(9001, themes[0], 3, seoulDateTime(), null, 1000));
let nextNotificationId = 25;
const connections = new Set();
const currentNotifications = () => notifications
  .filter((item) => item.userId === fixtureUser.id && item.deletedAt === null)
  .sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.id - a.id);
const publicNotification = ({ userId, deletedAt, ...item }) => item;
const closeConnection = (connection) => {
  connections.delete(connection);
  clearInterval(connection.heartbeat);
  clearTimeout(connection.timeout);
  if (!connection.res.writableEnded) connection.res.end();
};
const sendEvent = (connection, name, data) => {
  if (!sessions.has(connection.token) || connection.res.destroyed || connection.res.writableEnded) {
    closeConnection(connection);
    return;
  }
  try { connection.res.write(`event: ${name}\ndata: ${data}\n\n`); }
  catch { closeConnection(connection); }
};
const jsonResponse = (res, status = 200, data, code, message) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ status, ...(code ? { code } : {}),
    message: message || (status === 201 ? '성공적으로 생성되었습니다.' : '요청이 성공적으로 처리되었습니다.'),
    ...(data === undefined ? {} : { data }),
  }));
};
const fixtureError = (res, status, code, message) => jsonResponse(res, status, undefined, code, message);
const readJson = async (req) => {
  let input = '';
  for await (const chunk of req) input += chunk;
  return JSON.parse(input || '{}');
};
const handleNotificationFixture = async (req, res, url, route, token) => {
  if (!sessions.has(token)) {
    fixtureError(res, 401, 'CO08', '인증 정보가 유효하지 않습니다.');
    return;
  }
  const invalidInput = () => fixtureError(res, 400, 'CO01', '유효하지 않은 입력 값입니다.');
  const notFound = () => fixtureError(res, 404, 'CO03', '해당 엔티티를 찾을 수 없습니다.');
  if (route === '/users/me/interests/themes' && req.method === 'GET') {
    jsonResponse(res, 200, themes.filter((theme) => interests.has(theme.themeId))
      .map(({ themeId, themeName }) => ({ themeId, themeName })));
  } else if (route === '/users/me/interests/themes' && req.method === 'POST') {
    const body = await readJson(req);
    if (!Number.isSafeInteger(body?.themeId) || body.themeId < 1) return invalidInput();
    if (!themes.some((theme) => theme.themeId === body.themeId)) {
      return fixtureError(res, 404, 'TH01', '테마를 찾을 수 없습니다.');
    }
    if (interests.has(body.themeId)) return fixtureError(res, 409, 'IN01', '이미 등록한 관심 테마입니다.');
    interests.set(body.themeId, { notificationEnabled: true });
    jsonResponse(res, 201);
  } else if (/^\/users\/me\/interests\/themes\/\d+$/.test(route) && req.method === 'DELETE') {
    interests.delete(Number(route.split('/').at(-1)));
    jsonResponse(res);
  } else if (route === '/notifications' && req.method === 'GET') {
    const page = Number(url.searchParams.get('page') ?? 1);
    const size = Number(url.searchParams.get('size') ?? 20);
    if (!Number.isSafeInteger(page) || !Number.isSafeInteger(size) || page < 1 || size < 1 || size > 100) return invalidInput();
    const items = currentNotifications();
    const start = (page - 1) * size;
    jsonResponse(res, 200, { notifications: items.slice(start, start + size).map(publicNotification), page, size, hasNext: start + size < items.length });
  } else if (route === '/notifications/unread-count' && req.method === 'GET') {
    jsonResponse(res, 200, { unreadCount: currentNotifications().filter((item) => item.readAt === null).length });
  } else if (route === '/notifications/settings' && req.method === 'GET') {
    jsonResponse(res, 200, { enabled: notificationsEnabled });
  } else if (route === '/notifications/settings' && req.method === 'PATCH') {
    const body = await readJson(req);
    if (typeof body?.enabled !== 'boolean') return invalidInput();
    notificationsEnabled = body.enabled;
    jsonResponse(res);
  } else if (/^\/notifications\/themes\/\d+\/settings$/.test(route) && req.method === 'PATCH') {
    const body = await readJson(req);
    if (typeof body?.enabled !== 'boolean') return invalidInput();
    const interest = interests.get(Number(route.split('/')[3]));
    if (!interest) return notFound();
    interest.notificationEnabled = body.enabled;
    jsonResponse(res);
  } else if (route === '/notifications/read-all' && req.method === 'PATCH') {
    const now = seoulDateTime();
    currentNotifications().forEach((item) => { item.readAt ??= now; });
    jsonResponse(res);
  } else if (/^\/notifications\/\d+\/read$/.test(route) && req.method === 'PATCH') {
    const item = currentNotifications().find((entry) => entry.id === Number(route.split('/')[2]));
    if (!item) return notFound();
    item.readAt ??= seoulDateTime();
    jsonResponse(res);
  } else if (/^\/notifications\/\d+$/.test(route) && req.method === 'DELETE') {
    const item = currentNotifications().find((entry) => entry.id === Number(route.split('/')[2]));
    if (!item) return notFound();
    item.deletedAt = seoulDateTime();
    jsonResponse(res);
  } else if (route === '/notifications/subscribe' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', Connection: 'keep-alive' });
    const connection = { token, res };
    connections.add(connection);
    res.on('close', () => closeConnection(connection));
    connection.heartbeat = setInterval(() => sendEvent(connection, 'heartbeat', 'ping'), 15000);
    connection.timeout = setTimeout(() => closeConnection(connection), 5 * 60 * 1000);
    res.write('retry: 3000\n');
    sendEvent(connection, 'connected', 'connected');
  } else if (route === '/__fixtures/notifications/create' && req.method === 'POST') {
    // Local authenticated QA helper, never a production API. Simulates a scheduled batch.
    const body = await readJson(req);
    const themeId = body?.themeId ?? 1;
    const articleCount = body?.articleCount ?? 7;
    if (!Number.isSafeInteger(themeId) || !Number.isSafeInteger(articleCount) || articleCount < 1) return invalidInput();
    const theme = themes.find((item) => item.themeId === themeId);
    if (!theme) return notFound();
    if (!notificationsEnabled || !interests.get(themeId)?.notificationEnabled) {
      jsonResponse(res, 200, { created: false });
      return;
    }
    const item = notification(nextNotificationId++, theme, articleCount, seoulDateTime());
    notifications.push(item);
    connections.forEach((connection) => sendEvent(connection, 'notifications-changed', 'refresh'));
    jsonResponse(res, 201, publicNotification(item));
  } else {
    fixtureError(res, 404, 'CO13', '요청하신 리소스를 찾을 수 없습니다.');
  }
};
const port = Number(process.env.PORT || 5175);
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/v1') || url.pathname.startsWith('/__fixtures/')) {
    let data;
    let status = 200;
    const route = url.pathname.startsWith('/api/v1') ? url.pathname.slice('/api/v1'.length) : url.pathname;
    const analysisAvailable = !url.searchParams.has('asOf') || new Date(url.searchParams.get('asOf')) >= new Date(analysisSummary.windowEnd);
    const token = (req.headers.cookie || '').match(/(?:^|;\s*)fixture-session=([^;]+)/)?.[1];
    if (route === '/notifications' || route.startsWith('/notifications/') || route === '/users/me/interests/themes'
      || route.startsWith('/users/me/interests/themes/') || route.startsWith('/__fixtures/')) {
      try { await handleNotificationFixture(req, res, url, route, token); }
      catch (error) {
        if (error instanceof SyntaxError) fixtureError(res, 400, 'CO01', '유효하지 않은 입력 값입니다.');
        else { console.error(error); fixtureError(res, 500, 'CO99', '서버 내부 오류가 발생했습니다.'); }
      }
      return;
    }
    if (route === '/auth/login' && req.method === 'POST') {
      let input = ''; for await (const chunk of req) input += chunk;
      const credentials = JSON.parse(input || '{}');
      if (credentials.email === fixtureUser.email && credentials.password === 'preview1234') {
        const value = randomUUID(); sessions.add(value);
        res.setHeader('Set-Cookie', `fixture-session=${value}; Path=/; HttpOnly; SameSite=Lax`);
      } else status = 401;
    }
    else if (route === '/users/me') { if (sessions.has(token)) data = fixtureUser; else status = 401; }
    else if (route === '/auth/logout' && req.method === 'POST') {
      sessions.delete(token);
      connections.forEach((connection) => { if (connection.token === token) closeConnection(connection); });
      res.setHeader('Set-Cookie', 'fixture-session=; Path=/; Max-Age=0');
    }
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
    res.setHeader('Content-Type', ({ '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' })[path.extname(filename)] || 'application/octet-stream');
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
}).listen(port, '127.0.0.1', () => console.log(`Contract-fixture browser server: http://127.0.0.1:${port}`));
