// UI test for the Skills page (real page in jsdom against a real server). Needs Node: cd tests/ui && npm install jsdom
// Start the server first, with a throw-away skills folder:  SKILLS_DIR=/tmp/skl NEURACHAT_DB=/tmp/ui2.db python -m uvicorn main:app --port 8767
// then: node skills_test.js
const { JSDOM, VirtualConsole } = require('jsdom');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const BASE = 'http://127.0.0.1:8767';
(async () => {
  const errors = [], vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(String(e.message).slice(0, 120)));
  const opts = { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, BASE).href, o); w.confirm = () => true; } };
  const dom = await JSDOM.fromURL(BASE + '/skills', opts), w = dom.window, d = w.document, $ = s => d.querySelector(s);
  await sleep(1200);
  console.log('Skills page lists the bundled skills:', ['django-project', 'fastapi-service', 'python-cli', 'bugfix-workflow'].every(n => $('#list').textContent.includes(n)));
  $('#name').value = 'release-notes'; $('#desc').value = 'Use when writing release notes for our team.'; $('#body').value = 'Start with a one-line summary.';
  $('#add').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await sleep(900);
  console.log('added skill appears as a user skill:', $('#list').textContent.includes('release-notes') && $('#msg').textContent.startsWith('Saved'));
  [...d.querySelectorAll('#list .card')].find(c => c.textContent.includes('release-notes')).querySelector('button').click();
  await sleep(600);
  console.log('View shows the instructions:', [...d.querySelectorAll('#list pre')].some(p => p.textContent.includes('one-line summary')));
  $('#name').value = '../evil'; $('#desc').value = 'x'; $('#body').value = 'y';
  $('#add').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await sleep(700);
  console.log('a bad name is refused with a message:', $('#msg').className.includes('err'), '|', $('#msg').textContent.slice(0, 50));
  const del = [...d.querySelectorAll('#list .card')].find(c => c.textContent.includes('release-notes')).querySelectorAll('button')[1];
  del.click();
  await sleep(800);
  console.log('Delete removes it:', !$('#list').textContent.includes('release-notes'));
  const main = await JSDOM.fromURL(BASE + '/', Object.assign({}, opts, { beforeParse(w2) { w2.fetch = (u, o) => fetch(new URL(u, BASE).href, o); const stub = new Proxy(function () {}, { get: (t, k) => (k === 'then' ? undefined : stub), apply: (t, th, a) => a[0] }); w2.hljs = stub; w2.marked = stub; } }));
  await sleep(1200);
  const links = [...main.window.document.querySelectorAll('.sb-search a')].map(a => a.getAttribute('href'));
  console.log('chat sidebar links to Skills and Documents:', links.includes('/skills') && links.includes('/documents'));
  console.log('page script errors:', errors.length ? errors : 'none');
  process.exit(0);
})();
