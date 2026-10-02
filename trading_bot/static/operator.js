/* Progressive saved evidence reads. All authority stays in guarded server routes. */
(() => {
  'use strict';
  const navigation = document.querySelector('.navigation-disclosure');
  if (navigation) {
    const summary = navigation.querySelector('summary');
    const synchronizeNavigation = () => summary.setAttribute('aria-expanded', String(navigation.open));
    navigation.addEventListener('toggle', synchronizeNavigation);
    synchronizeNavigation();
  }
  const view = document.body.dataset.operatorView;
  const url = new URL(view ? '/api/views/' + encodeURIComponent(view) : '/api/session', location.origin);
  url.search = location.search;
  const parts = location.pathname.split('/');
  if (view === 'alerts' && /^[a-f0-9]{32}$/.test(parts[2] || '')) url.searchParams.set('episode_id', parts[2]);
  if (view && view.startsWith('validation-') && parts[3]) url.searchParams.set('result_id', parts[3]);
  if (view === 'record' || view === 'evidence') {
    url.searchParams.set('resource_id',decodeURIComponent(parts[2] || ''));
    url.searchParams.set('record_id',decodeURIComponent(parts[3] || ''));
  }
  if (!view) url.search = '';
  const button = document.querySelector('[data-refresh]');
  let timer, deadline, inFlight = false, stopped = false, controller, dirty = false;
  let currentSelection = null, lastAnnouncement = '', restorePending = false;
  function criticalKey(doc) {
    return Array.from(doc.querySelectorAll('.record-card[id^="incident-"]'))
      .filter(e => e.textContent.includes('CRITICAL') && e.textContent.includes('활성'))
      .map(e => e.id + ':' + (e.textContent.match(/revision\s+(\d+)/) || [,''])[1]).sort().join('|');
  }
  let lastCritical = criticalKey(document);
  const status = () => document.getElementById('refresh-status');
  function announce(text) {
    if (text !== lastAnnouncement && status()) { status().textContent = text; lastAnnouncement = text; }
  }
  function visible() { return document.visibilityState !== 'hidden'; }
  function schedule() {
    clearTimeout(timer);
    if (!stopped && visible()) timer = setTimeout(() => refresh(false), 30000);
  }
  function hideEvidence() {
    document.getElementById('operator-private').hidden = true;
  }
  function revealEvidence() {
    document.getElementById('operator-private').hidden = false;
  }
  function sessionEnded() {
    stopped = true; clearTimeout(timer); clearTimeout(deadline);
    if (controller) controller.abort();
    hideEvidence();
    // Remove sensitive cache nodes before offering reauthentication. Never replay POST.
    document.querySelectorAll('.operator-header, #main-content').forEach(e => e.replaceChildren());
    let box = document.getElementById('session-login');
    if (!box) { box = document.createElement('section'); box.id = 'session-login'; document.body.append(box); }
    const message = document.createElement('p');
    message.textContent = '로그인 시간이 만료되었습니다. 계속하려면 다시 로그인하세요.';
    const link = document.createElement('a'); link.href = '/login'; link.textContent = '로그인';
    box.replaceChildren(message, link);
  }
  function expiry(value) {
    const at = Date.parse(value);
    if (!Number.isFinite(at)) throw new Error('invalid session envelope');
    clearTimeout(deadline);
    // At the absolute boundary, conceal first, then ask the server. Browser time grants no access.
    deadline = setTimeout(() => {
      restorePending = true; hideEvidence();
      if (controller) controller.abort();
      refresh(false);
    }, at > Date.now() ? at - Date.now() : 30000);
  }
  function trustedDocument(html) {
    if (typeof html !== 'string' || html.length > 4 * 1024 * 1024) throw new Error('invalid render envelope');
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const main = doc.getElementById('main-content');
    if (!main || main.querySelector('script, iframe, object, embed, style')) throw new Error('invalid fragment');
    for (const element of main.querySelectorAll('*')) {
      for (const attr of element.attributes) {
        if (/^on/i.test(attr.name) || attr.name === 'srcdoc') throw new Error('invalid attribute');
        if (['href', 'src', 'action'].includes(attr.name)) {
          const target = new URL(attr.value, location.origin);
          if (target.origin !== location.origin || !['http:', 'https:'].includes(target.protocol)) throw new Error('invalid link');
        }
      }
    }
    return doc;
  }
  function replaceStatus(doc) {
    const old = document.getElementById('source-status'), fresh = doc.getElementById('source-status');
    if (old && fresh) old.replaceChildren(...Array.from(fresh.childNodes, n => document.importNode(n, true)));
    const oldCritical = document.querySelector('.critical-count'), freshCritical = doc.querySelector('.critical-count');
    if (oldCritical && freshCritical) {
      const target = new URL(freshCritical.getAttribute('href'), location.origin);
      if (target.origin !== location.origin || target.pathname !== '/alerts') throw new Error('invalid critical link');
      oldCritical.textContent = freshCritical.textContent;
      oldCritical.setAttribute('href', target.pathname + target.search);
    }
  }
  function apply(doc, keepDraft) {
    const old = document.getElementById('operator-evidence'), fresh = doc.getElementById('operator-evidence');
    if (!old || !fresh) throw new Error('missing evidence');
    const focused = document.activeElement;
    const key = focused && {id: focused.id, name: focused.name, href: focused.getAttribute('href')};
    const inputSelection = focused && typeof focused.selectionStart === 'number' ? [focused.selectionStart, focused.selectionEnd] : null;
    const selectedText = window.getSelection().toString();
    const drafts = Array.from(old.querySelectorAll('textarea, input:not([type=hidden]), select'), e =>
      ({id: e.id, name: e.name, value: e.value, checked: e.checked}));
    const disclosures = Array.from(old.querySelectorAll('details'), (e, i) => ({id: e.id, index:i, open:e.open}));
    const scroll = [window.scrollX, window.scrollY];
    const generated = old.querySelector('#generated-report');
    old.replaceChildren(...Array.from(fresh.childNodes, n => document.importNode(n, true)));
    if (generated && !old.querySelector('#generated-report')) old.append(generated);
    if (keepDraft) for (const saved of drafts) {
      const e = saved.id ? document.getElementById(saved.id) : Array.from(old.querySelectorAll('[name]')).find(e => e.name === saved.name);
      if (e) { e.value = saved.value; e.checked = saved.checked; }
    }
    const newDisclosures = old.querySelectorAll('details');
    for (const saved of disclosures) {
      const e = saved.id ? document.getElementById(saved.id) : newDisclosures[saved.index];
      if (e) e.open = saved.open;
    }
    let replacement = key && (key.id ? document.getElementById(key.id) :
      Array.from(old.querySelectorAll('a,button,input,textarea,select')).find(e => key.name ? e.name === key.name : key.href && e.getAttribute('href') === key.href));
    if (focused && old.contains(focused)) replacement = focused;
    if (replacement) {
      replacement.focus({preventScroll:true});
      if (inputSelection && replacement.setSelectionRange) replacement.setSelectionRange(...inputSelection);
    }
    if (selectedText) {
      const walker = document.createTreeWalker(old, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const index = node.textContent.indexOf(selectedText);
        if (index >= 0) { const range = document.createRange(); range.setStart(node,index); range.setEnd(node,index+selectedText.length);
          const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); break; }
      }
    }
    window.scrollTo(...scroll);
  }
  async function refresh(manual) {
    if (stopped || inFlight || (!manual && !visible() && !restorePending)) return;
    inFlight = true; clearTimeout(timer);
    controller = new AbortController();
    if (button) button.disabled = true;
    const timeout = setTimeout(() => controller.abort(),10000);
    if (manual) announce('저장 증거 조회 중…');
    try {
      const response = await fetch(url.href, {credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if (response.status === 401 || response.status === 403) { sessionEnded(); return; }
      if (!response.ok || new URL(response.url).origin !== location.origin) throw new Error('saved read failed');
      const data = await response.json(); expiry(data.expires_at);
      if (view) {
        if (data.view_id !== view || !['SUCCESS','FAILED'].includes(data.query_status)) throw new Error('invalid view envelope');
        const doc = trustedDocument(data.rendered_html);
        replaceStatus(doc);
        if (data.query_status === 'FAILED') throw new Error('saved source failed');
        const critical = criticalKey(doc);
        if (critical && critical !== lastCritical) {
          document.getElementById('critical-announcement').textContent = '새 CRITICAL 알림이 있습니다. 최신 원천 증거를 확인하세요.';
        }
        lastCritical = critical;
        const selection = window.getSelection();
        const focusedEvidence = document.getElementById('operator-evidence').contains(document.activeElement);
        const defer = !manual && (dirty || focusedEvidence || !selection.isCollapsed);
        if (defer) {
          announce(currentSelection !== data.selection_id || dirty ? '새 증거가 있습니다' : '저장 증거를 다시 조회했습니다.');
        } else {
          apply(doc, dirty);
          currentSelection = data.selection_id;
          announce('저장 증거를 다시 조회했습니다.');
        }
      } else announce('저장 증거를 다시 조회했습니다.');
      if (restorePending) { restorePending = false; revealEvidence(); }
    } catch (error) {
      if (!stopped) announce('저장 증거를 조회하지 못했습니다. 마지막 성공 관측을 유지합니다. 원천 상태를 확인한 뒤 다시 조회하세요.');
      // Failed cache revalidation never reveals concealed evidence.
    } finally {
      clearTimeout(timeout); inFlight = false; controller = null;
      if (button) button.disabled = false;
      schedule();
    }
  }
  document.addEventListener('input', event => {
    if (event.target.closest('[data-action-form]')) dirty = true;
  });
  document.addEventListener('submit', async event => {
    if (event.target.matches('.refresh-form') && view) { event.preventDefault(); refresh(true); return; }
    const form = event.target;
    if (!form.matches('[data-action-form]')) return;
    event.preventDefault();
    if (inFlight || stopped) return;
    inFlight = true; clearTimeout(timer);
    controller = new AbortController();
    const submits = form.querySelectorAll('[type=submit]'); submits.forEach(e => {e.disabled=true;});
    if (button) button.disabled = true;
    const timeout = setTimeout(() => controller.abort(),10000);
    try {
      const action = new URL(form.action,location.origin);
      if (action.origin !== location.origin) throw new Error('invalid form');
      const body = new FormData(form);
      const response = await fetch(action.href,{method:'POST',body,credentials:'same-origin',cache:'no-store',
        headers:{'X-CSRFToken':body.get('csrf_token')},signal:controller.signal});
      if (response.status===401 || response.status===403 || new URL(response.url).pathname==='/login') { sessionEnded(); return; }
      const doc = trustedDocument(await response.text());
      if (!response.ok && ![400,409,503].includes(response.status)) throw new Error('action failed');
      replaceStatus(doc); apply(doc,!response.ok);
      const error = doc.getElementById('error-summary');
      document.getElementById('error-summary').replaceChildren(...Array.from(error.childNodes,n=>document.importNode(n,true)));
      if (response.ok) {dirty=false; announce(doc.getElementById('refresh-status').textContent || '보고서를 생성했습니다.');}
      else {announce(error.textContent); document.getElementById('error-summary').focus({preventScroll:true});}
    } catch (error) {
      if (!stopped) announce('요청 결과를 확인할 수 없습니다. 입력 내용을 유지합니다. 최신 증거를 확인하세요.');
    } finally {
      clearTimeout(timeout); inFlight=false; controller=null;
      submits.forEach(e=>{e.disabled=false;}); if(button) button.disabled=false; schedule();
    }
  });
  document.addEventListener('visibilitychange',() => {
    clearTimeout(timer);
    if (visible()) refresh(false);
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) { restorePending=true; hideEvidence(); refresh(false); }
  });
  window.addEventListener('pagehide',() => { clearTimeout(timer); hideEvidence(); });
  if (document.body.dataset.expiresAt) expiry(document.body.dataset.expiresAt);
  schedule();
})();
