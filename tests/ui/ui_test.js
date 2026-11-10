// UI smoke test: loads the real page in jsdom against a real server and clicks through the sidebar.
// Run it (needs Node): 1) cd tests/ui && npm install jsdom
//   2) seed a throw-away database:  set NEURACHAT_DB=%TEMP%\ui.db  (Windows)  or  NEURACHAT_DB=/tmp/ui.db
//      python -c "import store; p=store.create_project('Thesis','Be formal'); a=store.create_chat(p); store.add_message(a,'user','Explain RAG'); store.add_message(a,'assistant','RAG = retrieve then generate'); b=store.create_chat(); store.add_message(b,'user','hello'); store.set_pinned(b,True)"
//   3) start the server on port 8765 with the same NEURACHAT_DB:  python -m uvicorn main:app --port 8765
//   4) node ui_test.js
const { JSDOM, VirtualConsole } = require('jsdom');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const BASE = 'http://127.0.0.1:8765';
const stub = new Proxy(function () {}, { get: (t, k) => (k === 'then' ? undefined : stub), apply: (t, th, a) => a[0] });
(async () => {
  const vc = new VirtualConsole(), errors = [];
  vc.on('jsdomError', e => errors.push(String(e.message).slice(0, 140)));
  const dom = await JSDOM.fromURL(BASE + '/', {
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, BASE).href, o);
      w.hljs = stub; w.marked = stub; w.mermaid = stub; w.Prism = stub;
      w.HTMLElement.prototype.scrollIntoView = () => {}; w.Element.prototype.scrollTo = () => {};
    },
  });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s);
  await sleep(1800);
  const side = $('#histArea').textContent;
  console.log('sidebar shows pinned chat, project and chat:', ['Pinned', 'hello', 'Projects', 'Thesis', 'Explain RAG'].every(t => side.includes(t)));
  [...d.querySelectorAll('#histArea .hist-item')].find(e => e.textContent.includes('Explain RAG')).click();
  await sleep(900);
  console.log('clicking a chat loads its messages:', $('#msgs').textContent.includes('RAG = retrieve then generate'), '| topbar:', $('#topTitle').textContent);
  [...d.querySelectorAll('#histArea .hist-proj')].find(e => e.textContent.includes('Thesis')).click();
  await sleep(500);
  console.log('clicking a project starts a chat in it:', $('#topTitle').textContent, '| welcome screen shown:', !!$('#welcome') && $('#msgs').textContent.indexOf('RAG = retrieve') < 0);
  $('.new-chat-btn').click();
  await sleep(500);
  console.log('New chat button works, welcome screen is back:', !!$('#welcome') && $('#welcome').style.display === '', '| topbar:', $('#topTitle').textContent);
  [...d.querySelectorAll('#histArea .hist-item')].find(e => e.textContent.includes('hello')).click();
  await sleep(700);
  console.log('pinned chat opens after a new chat:', $('#msgs').textContent.includes('hello'));
  const real = w.fetch;
  w.fetch = (u, o) => String(u).includes('/api/build')
    ? Promise.resolve({ ok: true, json: async () => ({ response: 'Built x', conv_id: 'zz', tool_calls: [], usage: { prompt: 1200, completion: 340, cost: 0.0003 } }) })
    : real(u, o);
  $('#inp').value = 'create a django project with login';
  w.send();
  await sleep(700);
  const modal = $('.modal-bg');
  console.log('project-request prompt appears:', !!modal, '|', modal && modal.textContent.slice(0, 60));
  if (modal) modal.querySelector('.modal-btn.primary').click();
  await sleep(1200);
  const msgs = $('#msgs').textContent;
  console.log('Build ran with token chips:', msgs.includes('1,200 in') && msgs.includes('340 out'), '| Build toggle on:', w.eval('state.modes.build'));
  w.fetch = (u, o) => { if (String(u).includes('/api/mcp/chat')) { w.__body = JSON.parse(o.body); return Promise.resolve({ ok: false, json: async () => ({ detail: 'stub' }) }); } return real(u, o); };
  w.eval("state.modes.build = false; state.modes.agent = false; document.querySelectorAll('.mode-toggle.on').forEach(b => b.classList.remove('on'))");
  $('#togAgent').click(); $('#togBuild').click();
  console.log('Agent and Build both on:', w.eval('state.modes.agent && state.modes.build'));
  $('#inp').value = 'create a django project with login';
  w.send();
  await sleep(900);
  console.log('request goes to the agent with build=true:', !!w.__body && w.__body.build === true && w.__body.stream === true);
  console.log('page script errors:', errors.length ? errors : 'none');
  process.exit(0);
})();
