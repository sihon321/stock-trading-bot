"""Real Chromium contracts: virtual timers and test-owned saved server only."""
from dataclasses import replace

import pytest
from playwright.sync_api import expect
from test_web_alert_routes import alert_web, report_web, setup, web

pytestmark = pytest.mark.browser


@pytest.fixture
def operator_app_kwargs(alert_web):
    app, _, _, _, _, _ = alert_web
    return dict(settings=app.extensions['web_settings'],
        evidence_service=app.extensions['evidence_service'], report_service=app.extensions['report_service'],
        alert_store=app.extensions['alert_store'], clock=app.extensions['operator_clock'])


def enter(page, server, clock, path='/account'):
    page.clock.install(time=clock())
    page.goto(server + '/login?return_to=' + path)
    page.get_by_label('운영자 계정', exact=True).fill('owner')
    page.get_by_label('비밀번호', exact=True).fill('synthetic-password')
    page.get_by_role('button', name='로그인', exact=True).click()
    # Login safely returns only fixed list pages. Visit authenticated detail explicitly.
    page.goto(server + path)
    expect(page.locator('#main-content')).to_be_visible()
    expect(page.locator('[data-refresh]')).to_be_enabled()


def test_visible_cadence_manual_and_source_time(operator_page, operator_server, alert_web):
    page = operator_page
    _, _, sources, _, _, _ = alert_web
    calls = []
    page.on('request',lambda r: calls.append(r.url) if '/api/views/account' in r.url else None)
    enter(page, operator_server, sources.clock)
    initial = page.locator('#source-status').inner_text()
    baseline = len(calls)
    sources.clock.advance(seconds=30)
    with page.expect_response('**/api/views/account*'):
        page.clock.run_for(30000)
    expect(page.locator('#refresh-status')).to_contain_text('다시 조회했습니다')
    assert len(calls) == baseline+1
    assert 'operator-snapshot' in page.locator('#main-content').inner_text()
    assert '원천 관측' in initial and '원천 관측' in page.locator('#source-status').inner_text()
    with page.expect_response('**/api/views/account*'):
        page.get_by_role('button',name='저장 증거 새로고침',exact=True).click()
    expect(page.locator('[data-refresh]')).to_be_enabled()
    assert len(calls) == baseline+2


def test_timeout_no_overlap_retains_last_success_and_then_recovers(operator_page, operator_server, alert_web):
    page = operator_page
    _, _, sources, _, _, _ = alert_web
    enter(page, operator_server, sources.clock)
    original = page.locator('#operator-evidence').inner_text()
    # The fake saved reader is delayed in the browser transport, not with real sleeps.
    page.evaluate("""() => { const saved = window.fetch; window.fetch = (...args) =>
      String(args[0]).includes('/api/views/account') ? new Promise((resolve,reject) => {
        window.delayedReads = (window.delayedReads || 0) + 1;
        args[1].signal.addEventListener('abort', () => reject(new DOMException('timeout','AbortError')));
      }) : saved(...args); window.restoreFetch = () => { window.fetch = saved; }; }""")
    page.get_by_role('button',name='저장 증거 새로고침',exact=True).click()
    expect(page.locator('[data-refresh]')).to_be_disabled()
    page.clock.run_for(9000)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    assert page.evaluate('window.delayedReads') == 1
    page.clock.run_for(1000)
    expect(page.locator('#refresh-status')).to_contain_text('마지막 성공 관측을 유지')
    assert page.locator('#operator-evidence').inner_text() == original
    page.evaluate('window.restoreFetch()')
    with page.expect_response('**/api/views/account*'):
        page.get_by_role('button',name='저장 증거 새로고침',exact=True).click()
    expect(page.locator('#refresh-status')).to_contain_text('다시 조회했습니다')


def test_dirty_note_focus_disclosure_scroll_and_explicit_refresh(operator_page, operator_server, alert_web):
    from trading_bot.alert_models import Severity
    page = operator_page
    _, _, sources, alerts, episode, fact = alert_web
    path = '/alerts/' + episode.episode_id
    enter(page, operator_server, sources.clock, path)
    note = page.get_by_label('대응 메모 (선택)',exact=True)
    note.fill('초안 보존 <script>bad()</script>')
    page.locator('#alert-evidence').evaluate('(e)=>e.open=true')
    note.focus()
    note.evaluate('(e)=>e.setSelectionRange(2,5)')
    page.evaluate('window.scrollTo(0,300)')
    position = page.evaluate('window.scrollY')
    alerts.observe(replace(fact,source_id='worsened-browser',sequence=2,severity=Severity.CRITICAL))
    with page.expect_response('**/api/views/alerts*'):
        page.clock.run_for(30000)
    expect(page.locator('#refresh-status')).to_contain_text('새 증거가 있습니다')
    expect(note).to_have_value('초안 보존 <script>bad()</script>')
    expect(note).to_be_focused()
    assert note.evaluate('(e)=>e.selectionStart') == 2
    assert page.locator('#alert-evidence').evaluate('(e)=>e.open')
    assert page.evaluate('window.scrollY') == position
    assert page.locator('[name=expected_revision]').input_value() == '1'
    with page.expect_response('**/api/views/alerts*'):
        page.get_by_role('button',name='저장 증거 새로고침',exact=True).click()
    expect(page.locator('[name=expected_revision]')).to_have_value('2')
    expect(page.get_by_label('대응 메모 (선택)',exact=True)).to_have_value('초안 보존 <script>bad()</script>')
    assert page.locator('#alert-evidence').evaluate('(e)=>e.open')
    assert page.evaluate('typeof window.bad') == 'undefined'


def test_hidden_pause_and_one_read_on_return(operator_page, operator_server, alert_web):
    page = operator_page
    _, _, sources, _, _, _ = alert_web
    calls=[]
    page.on('request',lambda r: calls.append(r.url) if '/api/views/account' in r.url else None)
    enter(page,operator_server,sources.clock)
    baseline=len(calls)
    page.evaluate("Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'}); document.dispatchEvent(new Event('visibilitychange'))")
    page.clock.run_for(90000)
    assert len(calls)==baseline
    with page.expect_response('**/api/views/account*'):
        page.evaluate("Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'}); document.dispatchEvent(new Event('visibilitychange'))")
    expect(page.locator('[data-refresh]')).to_be_enabled()
    assert len(calls)==baseline+1


@pytest.mark.parametrize('boundary',['expiry','revoked','restore'])
def test_session_boundary_hides_cached_evidence_no_post_replay(operator_page, operator_server, alert_web, boundary):
    page=operator_page
    app,_,sources,_,_,_=alert_web
    posts=[]
    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' and '/login' not in r.url else None)
    enter(page,operator_server,sources.clock)
    if boundary=='expiry':
        sources.clock.advance(hours=12)
    else:
        app.extensions['web_store'].revoke_all_sessions(sources.clock())
    if boundary=='restore':
        with page.expect_response('**/api/views/account*'):
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
    else:
        with page.expect_response('**/api/views/account*'):
            page.clock.run_for(30000)
    expect(page.locator('#session-login')).to_be_visible()
    expect(page.locator('#main-content')).to_be_hidden()
    assert 'operator-snapshot' not in page.locator('body').inner_text()
    assert not posts


def test_failed_saved_source_retains_attribution(operator_page,operator_server,alert_web):
    page=operator_page
    _,_,sources,_,_,_=alert_web
    enter(page,operator_server,sources.clock)
    before=page.locator('#operator-evidence').inner_text()
    metadata=page.locator('#source-status').inner_text()
    sources.clock.advance(minutes=10)
    sources.paths['audit'].rename(sources.paths['audit'].with_suffix('.missing'))
    with page.expect_response('**/api/views/account*'):
        page.get_by_role('button',name='저장 증거 새로고침',exact=True).click()
    expect(page.locator('#refresh-status')).to_contain_text('마지막 성공 관측을 유지')
    assert page.locator('#operator-evidence').inner_text()==before
    expect(page.locator('#source-status')).to_contain_text('조회 실패')
    assert '원천 관측' in metadata


def test_enhanced_ack_conflict_retains_draft_then_server_success(operator_page,operator_server,alert_web):
    from trading_bot.alert_models import Severity
    page=operator_page
    _,_,sources,alerts,episode,fact=alert_web
    enter(page,operator_server,sources.clock,'/alerts/'+episode.episode_id)
    note=page.get_by_label('대응 메모 (선택)',exact=True)
    note.fill('확인 중')
    alerts.observe(replace(fact,source_id='post-worse',sequence=2,severity=Severity.CRITICAL))
    with page.expect_response('**/ack') as reply:
        page.get_by_role('button',name='읽음으로 기록',exact=True).click()
    assert reply.value.status==409
    expect(page.locator('#error-summary')).to_contain_text('알림 상태가 변경되었습니다')
    expect(note).to_have_value('확인 중')
    expect(page.locator('[name=expected_revision]')).to_have_value('2')
    assert not alerts.get_incident(episode.episode_id).acknowledged
    with page.expect_response('**/ack') as reply:
        page.get_by_role('button',name='읽음으로 기록',exact=True).click()
    assert reply.value.status==200
    expect(page.locator('#refresh-status')).to_contain_text('읽음으로 기록했습니다')
    assert alerts.get_incident(episode.episode_id).active
    assert alerts.list_acknowledgements(episode.episode_id)[0].actor=='owner'


def test_enhanced_report_three_real_downloads(operator_page,operator_server,alert_web):
    page=operator_page
    _,_,sources,_,_,_=alert_web
    enter(page,operator_server,sources.clock,'/reports')
    replay=page.locator('form:has([name=family][value=replay])')
    with page.expect_response('**/reports/generate'):
        replay.get_by_role('button',name='보고서 생성',exact=True).click()
    expect(page.locator('#generated-report')).to_be_visible()
    for fmt in ['TXT','JSON','CSV']:
        with page.expect_download() as download:
            page.get_by_role('link',name=fmt+' 내려받기',exact=True).click()
        assert download.value.failure() is None
        assert download.value.suggested_filename.endswith('.'+fmt.lower())


def test_record_detail_timer_uses_same_saved_selection(operator_page,operator_server,alert_web):
    page=operator_page
    _,_,sources,_,_,_=alert_web
    enter(page,operator_server,sources.clock,'/records/audit/runs%3Aoperator-run')
    before=page.locator('#operator-evidence').inner_text()
    with page.expect_response('**/api/views/record*'):
        page.clock.run_for(30000)
    expect(page.locator('#refresh-status')).to_contain_text('다시 조회했습니다')
    assert page.locator('#operator-evidence').inner_text()==before


def test_native_report_download_and_blank_ack_without_javascript(browser,operator_server,alert_web):
    from urllib.parse import urlsplit
    from operator_fixtures import capture_sources
    _,_,sources,alerts,episode,_=alert_web
    before=capture_sources(sources)
    violations=[]
    origin=urlsplit(operator_server)
    with browser.new_context(java_script_enabled=False,accept_downloads=True,service_workers='block') as context:
        def local(route):
            if urlsplit(route.request.url)[:2]==origin[:2]:
                route.continue_()
            else:
                violations.append(route.request.url)
                route.abort()
        context.route('**/*',local)
        page=context.new_page()
        page.set_default_timeout(5000)
        page.goto(operator_server+'/login?return_to=/reports')
        page.get_by_label('운영자 계정',exact=True).fill('owner')
        page.get_by_label('비밀번호',exact=True).fill('synthetic-password')
        page.get_by_role('button',name='로그인',exact=True).click()
        page.locator('form:has([name=family][value=replay])').get_by_role('button',name='보고서 생성',exact=True).click()
        expect(page.locator('#generated-report')).to_be_visible()
        for fmt in ['TXT','JSON','CSV']:
            with page.expect_download() as download:
                page.get_by_role('link',name=fmt+' 내려받기',exact=True).click()
            assert download.value.failure() is None
        page.goto(operator_server+'/alerts/'+episode.episode_id)
        page.get_by_role('button',name='읽음으로 기록',exact=True).click()
        expect(page.locator('#refresh-status')).to_contain_text('읽음으로 기록했습니다')
        assert alerts.get_incident(episode.episode_id).active
        assert alerts.list_acknowledgements(episode.episode_id)[0].note==''
    assert not violations
    assert capture_sources(sources)==before
