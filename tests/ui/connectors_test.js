// UI test for the Connectors page. Needs Node: cd tests/ui && npm install jsdom
// Start the server with throw-away files:  CONNECTORS_FILE=/tmp/conn.json NEURACHAT_DB=/tmp/ui5.db python -m uvicorn main:app --port 8769
// then: node connectors_test.js   (BASE=http://127.0.0.1:<port> overrides the address)
const { JSDOM, VirtualConsole } = require('jsdom');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const BASE = process.env.BASE || 'http://127.0.0.1:8769';
(async () => {
  const errors = [], vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(String(e.message).slice(0, 120)));
  const dom = await JSDOM.fromURL(BASE + '/connectors', { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, BASE).href, o); w.confirm = () => true; } });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s);
  await sleep(1000);
  console.log('empty state is explained:', $('#list').textContent.includes('No connectors yet'));
  d.querySelector('[data-preset="github"]').click();
  console.log('the GitHub preset fills the form:', $('#name').value === 'github' && $('#base').value === 'https://api.github.com' && $('#tokenenv').value === 'GITHUB_TOKEN');
  $('#add').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await sleep(900);
  console.log('saved connector is listed, read-only, token flagged as not set:', ['github', 'api.github.com', 'read-only', 'NOT set'].every(t => $('#list').textContent.includes(t)));
  $('#name').value = 'bad'; $('#desc').value = 'x'; $('#base').value = 'http://plain.example'; $('#tokenenv').value = 'ghp_realtoken123';
  $('#add').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await sleep(700);
  console.log('a plain http URL is refused with a message:', $('#msg').className.includes('err'), '|', $('#msg').textContent.slice(0, 60));
  $('#base').value = 'https://ok.example';
  $('#add').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await sleep(700);
  console.log('a pasted token (instead of a variable name) is refused:', $('#msg').className.includes('err') && /NAME of an environment variable/.test($('#msg').textContent));
  [...d.querySelectorAll('#list .card')].find(c => c.textContent.includes('github')).querySelectorAll('button')[1].click();
  await sleep(800);
  console.log('Delete removes it:', !$('#list').textContent.includes('api.github.com'));
  console.log('page script errors:', errors.length ? errors : 'none');
  process.exit(0);
})();
