// UI test for the Models page (the download states are simulated, so nothing is downloaded). Needs Node: cd tests/ui && npm install jsdom
// Start the server:  AUTO_DOWNLOAD_MODELS=0 NEURACHAT_DB=/tmp/ui8.db python -m uvicorn main:app --port 8770
// then: BASE=http://127.0.0.1:8770 node models_test.js
const { JSDOM, VirtualConsole } = require('jsdom');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const BASE = process.env.BASE || 'http://127.0.0.1:8768';
(async () => {
  const errors = [], vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(String(e.message).slice(0, 120)));
  let phase = 0; const posts = [];
  const model = (name, status, progress) => ({ name, repo: 'org/' + name, size_mb: 100, purpose: 'purpose of ' + name, status, progress, error: '' });
  const fake = (u, o) => {
    u = String(u);
    if (u.startsWith('/api/local-models') && !(o && o.method === 'POST')) {
      const st = [['missing', 0], ['downloading', 0.4], ['ready', 1]][Math.min(phase, 2)];
      return Promise.resolve({ ok: true, json: async () => ({ models: [model('embedder', ...st), model('reranker', 'ready', 1)], hf_token: false, auto: true }) });
    }
    if (u.includes('/download')) { posts.push(u); phase = 1; return Promise.resolve({ ok: true, json: async () => ({ started: true }) }); }
    return fetch(new URL(u, BASE).href, o);
  };
  const dom = await JSDOM.fromURL(BASE + '/models', { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) { w.fetch = fake; } });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s);
  await sleep(900);
  const first = $('#local').textContent;
  console.log('a missing model is shown with a Download button:', first.includes('Not downloaded') && first.includes('Ready') && !$('#local .card button').disabled);
  $('#local .card button').click();
  await sleep(700);
  console.log('Download was requested and a progress bar appears:', posts.length === 1 && posts[0].includes('/api/local-models/embedder/download') && $('#local').textContent.includes('Downloading 40%') && !!$('#local .bar i'));
  phase = 2;
  await sleep(2200);
  console.log('the page notices when the download finished:', $('#local').textContent.includes('Ready') && !$('#local').textContent.includes('Downloading') && $('#all').disabled);
  console.log('cloud models section renders:', $('#cloud').textContent.length > 0);
  console.log('page script errors:', errors.length ? errors : 'none');
  process.exit(0);
})();
