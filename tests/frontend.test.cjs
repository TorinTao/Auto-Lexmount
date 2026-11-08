// Logic tests with a small DOM double; not a replacement for real browser QA.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../autolex/web/app.js'), 'utf8');

function harness() {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      innerHTML: '', textContent: '', dataset: {}, hidden: false, disabled: false, open: false,
      classList: { toggle() {} }, setAttribute() {}, addEventListener() {}, focus() {},
      showModal() { this.open = true; }, close() { this.open = false; }, scrollIntoView() {},
    });
    return nodes.get(selector);
  }
  const requests = [];
  const context = vm.createContext({
    document: { querySelector: node, querySelectorAll: () => [], addEventListener() {}, hidden: false },
    window: { scrollTo() {} }, navigator: {}, URL, AbortSignal, console,
    setInterval() {}, setTimeout() { return 1; }, clearTimeout() {},
    fetch: async (url, options) => {
      requests.push({ url, options });
      const data = url === '/api/health' ? { token: 'test-token', configuration: { lexmount: true, model: false, docker: false } }
        : url === '/api/runs' && options.method === 'POST' ? { id: 'test-run' }
        : url === '/api/runs' ? { runs: [] }
        : { state: { id: 'test-run', demo: true, status: 'ready', completed: ['rules', 'ideas', 'build', 'test', 'package'] }, artifacts: [] };
      return { ok: true, json: async () => data };
    }
  });
  // Skip automatic boot only; execute all the same production helpers and event registrations.
  vm.runInContext(script.replace('health().then(refresh);', ''), context);
  return { node, requests, run: (code) => vm.runInContext(code, context) };
}

test('empty state and all five stages render', () => {
  const h = harness();
  assert.match(h.node('#result-content').innerHTML, /你的下一个作品/);
  const pipeline = h.node('#pipeline').innerHTML;
  for (const title of ['读取规则', '生成选题', '生成代码', '测试修复', '材料打包']) assert.ok(pipeline.includes(title));
});

test('HTML and dangerous links are escaped', () => {
  const h = harness();
  assert.equal(h.run('esc("<script>alert(1)</script>")'), '&lt;script&gt;alert(1)&lt;/script&gt;');
  assert.equal(h.run('safeLink("javascript:alert(1)")'), '');
  assert.equal(h.run('safeLink("file:///etc/passwd")'), '');
  assert.equal(h.run('safeLink("https://example.com")'), 'https://example.com/');
});

test('demo results remain labelled and untrusted text is inert', () => {
  const h = harness();
  h.run(`store.detail = {state:{demo:true}, output:{items:[{title:'<img onerror=alert(1)>',summary:'A summary',url:'javascript:alert(1)'}]}}; renderOutput()`);
  const html = h.node('#result-content').innerHTML;
  assert.match(html, /离线固定样例/);
  assert.match(html, /&lt;img/);
  assert.ok(!html.includes('href="javascript:'));
});

test('changing selected run clears render cache', () => {
  const h = harness();
  h.run(`store.detail={state:{demo:true},output:{items:[{title:'Example',summary:'Summary',url:'https://example.com'}]}}; renderOutput(); var old=store.detail; store.detail=null; renderOutput(); store.detail=old; renderOutput()`);
  assert.match(h.node('#result-content').innerHTML, /Example/);
});

test('test tab shows failures and actual return code', () => {
  const h = harness();
  h.run(`store.tab='tests'; store.detail={state:{demo:true},tests:{passed:false,attempts:[{attempt:1,returncode:2,failures:['Missing output'],log:'<unsafe>'}]}};renderOutput()`);
  const html = h.node('#result-content').innerHTML;
  assert.match(html, /退出码 2/);
  assert.match(html, /Missing output/);
  assert.match(html, /&lt;unsafe&gt;/);
});

test('code tab escapes generated source', () => {
  const h = harness();
  h.run(`store.tab='code';store.detail={state:{demo:true},code:'print("<script>")'};renderOutput()`);
  assert.match(h.node('#result-content').innerHTML, /&lt;script&gt;/);
  assert.match(h.node('#result-content').innerHTML, /main.py/);
});

test('material links only expose available artifacts', () => {
  const h = harness();
  h.run(`store.tab='materials';store.selected='run-1';store.detail={state:{demo:true},report:'A report',artifacts:['submission.zip']};renderOutput()`);
  const html = h.node('#result-content').innerHTML;
  assert.match(html, /\/api\/runs\/run-1\/files\/submission.zip/);
  assert.ok(!html.includes('/files/tests.json'));
  assert.match(html, /尚无提交回执/);
});

test('active job disables launches and completed state hides resume', () => {
  const h = harness();
  h.run(`store.online=true;store.runs=[{state:{active:true}}];store.detail={state:{id:'run-1',status:'ready',demo:true,completed:['rules','ideas','build','test','package']}};renderPipeline()`);
  assert.equal(h.node('#quick-demo').disabled, true);
  assert.equal(h.node('#new-task').disabled, true);
  assert.equal(h.node('#resume-task').hidden, true);
});

test('health and launch send CSRF token and select created run', async () => {
  const h = harness();
  await h.run('health()');
  assert.equal(h.run('store.token'), 'test-token');
  await h.run(`launch({url:'https://example.com',mode:'demo'})`);
  const post = h.requests.find((request) => request.options.method === 'POST');
  assert.equal(post.options.headers['X-Autolex-Token'], 'test-token');
  assert.equal(JSON.parse(post.options.body).mode, 'demo');
  assert.equal(h.run('store.selected'), 'test-run');
  assert.equal(h.run('store.busy'), false);
});

test('connection failure shows recovery instructions and disables execution', async () => {
  const h = harness();
  h.run(`fetch=async()=>{throw new Error('offline')}`);
  await h.run('health()');
  assert.equal(h.node('#offline-banner').hidden, false);
  assert.equal(h.node('#quick-demo').disabled, true);
});

test('HTTP API errors surface instead of claiming success', async () => {
  const h = harness();
  h.run(`fetch=async()=>({ok:false,status:400,json:async()=>({error:'模型尚未配置'})})`);
  await assert.rejects(h.run(`api('/api/runs',{})`), /模型尚未配置/);
});

test('overview explains results, usage and next step', () => {
  const h=harness();
  h.run(`store.detail={state:{id:'r1',status:'ready',demo:false,completed:['build'],model_calls:4,model_budget:20},artifacts:['index.html'],summary:{sources:2,points:5,attempts:3,parent:'r0',next_step:'核对原文'}}; renderPipeline()`);
  const html=h.node('#run-overview').innerHTML;
  assert.match(html,/2 个来源 · 5 条依据/);
  assert.match(html,/4 \/ 20/);
  assert.match(html,/核对原文/);
  assert.equal(h.node('#open-preview').href,'/api/runs/r1/preview');
});

test('history uses meaningful titles and retains run identifiers', () => {
  const h=harness();
  h.run(`store.runs=[{state:{id:'opaque-run',status:'ready',completed:[]},summary:{title:'CSV 选择指南',parent:'previous-run'}}];renderHistory()`);
  const html=h.node('#history-body').innerHTML;
  assert.match(html,/CSV 选择指南/);
  assert.match(html,/opaque-run/);
  assert.match(html,/previous-run/);
});

test('resumed test history is visible and escaped', () => {
  const h=harness();
  h.run(`store.tab='tests';store.detail={state:{demo:false},test_history:[{attempts:[{attempt:1,failures:['<old failure>']}]}]};renderOutput()`);
  assert.match(h.node('#result-content').innerHTML,/恢复前/);
  assert.match(h.node('#result-content').innerHTML,/&lt;old failure&gt;/);
});

test('revision dialog explains the inherited live or demo mode', () => {
  const h = harness();
  h.run(`store.selected='parent';store.detail={state:{demo:false,url:'https://example.com',brief:'Keep topic'}};openTaskDialog(true)`);
  assert.match(h.node('#mode-help').textContent, /API 和 Docker/);
  assert.equal(h.node('#revision-of').value, 'parent');
  assert.equal(h.node('#task-url').readOnly, true);
  h.run('store.detail.state.demo=true;openTaskDialog(true)');
  assert.match(h.node('#mode-help').textContent, /DEMO/);
});

test('publication controls stay bound to the selected live work', () => {
  const h=harness();
  h.run(`store.detail={state:{id:'generated',demo:false,status:'ready',completed:['package']},release_configured:true,artifacts:[]};renderPipeline()`);
  assert.equal(h.node('#release-task').hidden,false);
  h.run(`store.detail.release={status:'submitted',url:'https://yours.lexmount.cn/artifact-site/s/own-work',passcode:'CODE12',receipt:{id:'receipt-for-work'}};renderPipeline()`);
  assert.equal(h.node('#release-task').hidden,true);
  assert.match(h.node('#release-summary').innerHTML,/own-work/);
  assert.match(h.node('#release-summary').innerHTML,/receipt-for-work/);
  h.run('store.detail.release=null;store.detail.state.demo=true;renderPipeline()');
  assert.equal(h.node('#release-task').hidden,true);
});

test('quote support failures are visible and escaped', () => {
  const h=harness();
  h.run(`store.tab='tests';store.detail={state:{demo:false},tests:{passed:false,attempts:[]},citations:{passed:false,checks:[{id:'p1',passed:false,reason:'<unsupported>'}]}};renderOutput()`);
  assert.match(h.node('#result-content').innerHTML,/引用支撑检查 · 未通过/);
  assert.match(h.node('#result-content').innerHTML,/&lt;unsupported&gt;/);
});
