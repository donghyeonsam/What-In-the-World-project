import test from 'node:test';
import assert from 'node:assert/strict';
import React, { act } from 'react';
import { createServer } from 'vite';
import { JSDOM, VirtualConsole } from 'jsdom';

test('user can compare countries, filter articles, sign in, bookmark and restore URL state', async () => {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost:5175', pretendToBeVisual: true, virtualConsole: new VirtualConsole() });
  const previous = new Map();
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, IS_REACT_ACT_ENVIRONMENT: true })) { previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, { configurable: true, writable: true, value }); }
  // A DOM test cannot render WebGL; exercise the app's real no-WebGL fallback.
  dom.window.HTMLCanvasElement.prototype.getContext = () => null;
  const originalError = console.error;
  const errors = [];
  console.error = (...args) => { if (!String(args[0]).includes('Error creating WebGL context')) errors.push(args.join(' ')); };
  const vite = await createServer({ configFile: false, server: { middlewareMode: true }, appType: 'custom', esbuild: { jsx: 'automatic' }, optimizeDeps: { noDiscovery: true, include: [] } });
  const { createRoot } = await import('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  const flush = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); }); };
  const click = async element => { assert.ok(element, 'Expected visible control exists'); await act(async () => { element.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })); }); await flush(); };
  const button = (text, scope = document) => [...scope.querySelectorAll('button')].find(el => el.textContent.includes(text));
  const fill = async (input, value) => { assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new dom.window.Event('input', { bubbles: true })); }); };
  try {
    const { default: App } = await vite.ssrLoadModule('/src/App.jsx');
    await act(async () => { root.render(React.createElement(App)); }); await flush();
    assert.match(document.body.textContent, /같은 세계, 다른 시선/);
    assert.match(document.body.textContent, /지구본을 표시할 수 없습니다/);
    await click(button('반도체 공급망 재편'));
    assert.equal(new URLSearchParams(location.search).get('issue'), '101');
    await click(button('한국', document.querySelector('.country-buttons')));
    await click(button('미국', document.querySelector('.country-buttons')));
    assert.equal(document.querySelectorAll('.comparison-column').length, 2);
    assert.equal(new URLSearchParams(location.search).get('issue'), '101');
    assert.equal(new URLSearchParams(location.search).get('compare'), 'KR,US');
    await click(document.querySelector('.comparison-column .article-title'));
    assert.ok(new URLSearchParams(location.search).get('article'));
    assert.match(document.querySelector('[role="dialog"]').textContent, /가상 데이터/);
    await click(button('기사 저장', document.querySelector('[role="dialog"]')));
    assert.match(document.querySelector('[role="dialog"]').textContent, /다시 만나 반가워요/);
    await fill(document.querySelector('input[type="email"]'), 'demo@example.com');
    await fill(document.querySelector('input[type="password"]'), 'demo-pass-123');
    await act(async () => { document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })); }); await flush();
    assert.ok(!document.querySelector('[role="dialog"]'));
    await click(button('내 뉴스', document.querySelector('nav')));
    assert.match(document.body.textContent, /demo@example.com/);
    assert.equal(document.querySelectorAll('.my-news .article-row').length, 1);
    await click(button('관심사 설정'));
    await click(button('대한민국', document.querySelector('.interest-options')));
    assert.equal(button('대한민국', document.querySelector('.interest-options')).getAttribute('aria-pressed'), 'true');
    await click(button('나를 위한 뉴스'));
    assert.ok(document.querySelectorAll('.my-news .article-row').length > 0);
    await click(button('뉴스 둘러보기', document.querySelector('nav')));
    await click(button('반도체 & 공급망', document.querySelector('.theme-chips')));
    assert.equal(new URLSearchParams(location.search).get('theme'), '11');
    assert.equal(document.querySelectorAll('.article-row').length, 12);
    await click(button('기사 더 보기'));
    assert.equal(document.querySelectorAll('.article-row').length, 15);
    // Browser back event reconstructs the same issue and comparison state.
    await act(async () => { dom.window.history.pushState({}, '', '/?issue=102&compare=JP'); dom.window.dispatchEvent(new dom.window.PopStateEvent('popstate')); }); await flush();
    assert.match(document.body.textContent, /혁신과 규칙 사이/);
    assert.equal(document.querySelectorAll('.comparison-column').length, 1);
    await act(async () => { dom.window.history.pushState({}, '', '/?article=demo-101-KR-0'); dom.window.dispatchEvent(new dom.window.PopStateEvent('popstate')); }); await flush();
    assert.match(document.querySelector('[role="dialog"]').textContent, /국내 산업의 기회와 과제/);
    await click(document.querySelector('[aria-label="닫기"]'));
    assert.equal(new URLSearchParams(location.search).get('article'), null);
    await click(button('데이터 설정'));
    await click(button('기존 API 연결'));
    await flush();
    assert.match(document.body.textContent, /데이터를 불러오지 못했어요/);
    assert.match(document.body.textContent, /실제 API 오류를 데모 데이터로 대체하지 않습니다/);
    assert.equal(errors.length, 0, errors.join('\n'));
  } finally {
    await act(async () => root.unmount());
    await vite.close(); dom.window.close(); console.error = originalError;
    for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  }
});
