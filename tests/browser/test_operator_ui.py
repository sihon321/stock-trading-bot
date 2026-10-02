"""Real Chromium acceptance for every Korean saved-evidence destination."""
from pathlib import Path
from urllib.parse import urlsplit
import csv
import io
import json

import pytest
from playwright.sync_api import expect
from test_web_alert_routes import alert_web, report_web, setup, web

pytestmark = pytest.mark.browser


@pytest.fixture
def operator_app_kwargs(alert_web):
    app, _, _, _, _, _=alert_web
    return dict(settings=app.extensions['web_settings'],evidence_service=app.extensions['evidence_service'],
        report_service=app.extensions['report_service'],alert_store=app.extensions['alert_store'],
        clock=app.extensions['operator_clock'])


def enter(page,origin,path='/'):
    page.goto(origin+'/login')
    page.get_by_label('운영자 계정',exact=True).fill('owner')
    page.get_by_label('비밀번호',exact=True).fill('synthetic-password')
    page.get_by_role('button',name='로그인',exact=True).click()
    page.goto(origin+path)
    expect(page.locator('#main-content')).to_be_visible()


MEASURE = """() => {
  const rgb = color => color.match(/[\\d.]+/g).map(Number);
  const lum = c => c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
    .reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
  const ratio = (a,b) => (Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
  const background = el => { for(let node=el;node;node=node.parentElement) {
    const c=rgb(getComputedStyle(node).backgroundColor); if(c.length<4 || c[3]>0) return c;
  } return [255,255,255]; };
  const visible = el => el.getClientRects().length && getComputedStyle(el).visibility==='visible';
  const text=[], controls=[], targets=[], motion=[], tables=[];
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()) {
    const node=walker.currentNode,el=node.parentElement;
    if(!node.textContent.trim() || !el || !visible(el) || ['SCRIPT','STYLE','OPTION'].includes(el.tagName)) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    if(!range.getBoundingClientRect().width) continue;
    const contrast=ratio(rgb(getComputedStyle(el).color),background(el));
    text.push({text:node.textContent.trim().slice(0,60),contrast});
  }
  for(const el of document.querySelectorAll('button,input:not([type=hidden]),select,textarea,summary,a')) {
    if(!visible(el)) continue;
    const r=el.getBoundingClientRect(),s=getComputedStyle(el),bg=background(el.parentElement);
    targets.push({tag:el.tagName,text:el.textContent.trim().slice(0,50),width:r.width,height:r.height});
    if(['BUTTON','INPUT','SELECT','TEXTAREA'].includes(el.tagName)) {
      controls.push({text:el.name||el.textContent.trim(),contrast:ratio(rgb(s.borderTopColor),bg)});
    }
    motion.push(s.animationDuration==='0s' && s.transitionDuration==='0s');
  }
  for(const el of document.querySelectorAll('.table-scroll')) {
    if(visible(el)) tables.push({wide:el.scrollWidth>el.clientWidth,overflow:getComputedStyle(el).overflowX,
      named:!!el.getAttribute('aria-label') || !!document.getElementById(el.getAttribute('aria-labelledby')),
      focusable:el.tabIndex===0});
  }
  const focus=document.activeElement,fs=getComputedStyle(focus);
  return {text,controls,targets,motion,tables,overflow:document.documentElement.scrollWidth>innerWidth+1,
    body:getComputedStyle(document.body).backgroundColor,focus:{width:fs.outlineWidth,
      contrast:ratio(rgb(fs.outlineColor),background(focus.parentElement))}};
}"""


def assert_rendered_contract(page,width,theme):
    facts=page.evaluate(MEASURE)
    assert not facts['overflow'],page.url
    assert facts['body']==('rgb(248, 250, 252)' if theme=='light' else 'rgb(11, 18, 32)')
    assert facts['text'] and all(t['contrast']>=4.5 for t in facts['text']), [
        t for t in facts['text'] if t['contrast']<4.5]
    assert all(c['contrast']>=3 for c in facts['controls']),facts['controls']
    assert all(t['height']>=43.9 and t['width']>=43.9 for t in facts['targets']), [
        t for t in facts['targets'] if t['height']<43.9 or t['width']<43.9]
    assert all(facts['motion'])
    assert all(t['overflow']=='auto' and t['named'] and t['focusable'] for t in facts['tables'])
    assert page.locator('html').get_attribute('lang')=='ko'
    assert page.locator('#main-content h1').count()==1
    assert page.locator('#refresh-status').get_attribute('aria-live')=='polite'
    for badge in page.locator('.badge').all():
        assert badge.inner_text().strip()
        assert badge.locator('svg[aria-hidden=true]').count()==1


@pytest.mark.parametrize('width',[1280,390,320])
@pytest.mark.parametrize('theme',['light','dark'])
def test_every_destination_detail_theme_contrast_and_mobile_targets(operator_page,operator_server,width,theme):
    page=operator_page
    page.set_viewport_size({'width':width,'height':900})
    page.emulate_media(color_scheme=theme,reduced_motion='reduce')
    enter(page,operator_server)
    paths=page.locator('#operator-navigation a').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))')
    assert len(paths)==len(set(paths))==17
    for path in paths:
        page.locator('#operator-navigation a[href="'+path+'"]').click()
        expect(page.locator('#main-content h1')).to_be_visible()
        assert page.locator('#operator-navigation [aria-current=page]').get_attribute('href')==path
        assert_rendered_contract(page,width,theme)
        # Every saved detail/evidence link on that destination is usable at its current size.
        links=page.locator('#operator-evidence a').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))')
        for detail in sorted(set(p for p in links if p and p.startswith(('/records/','/evidence/')))):
            page.goto(operator_server+detail)
            expect(page.locator('#main-content h1')).to_be_visible()
            assert_rendered_contract(page,width,theme)
            evidence=page.locator('a[href^="/evidence/"]')
            if evidence.count():
                evidence.first.click()
                expect(page.locator('#main-content')).to_contain_text('정제된 원천 증거')
                assert_rendered_contract(page,width,theme)
            page.goto(operator_server+path)
        if path.startswith('/validation/'):
            if path.endswith(('calibration','readiness')):
                expect(page.locator('#main-content')).to_contain_text('참고용 평가 · 실거래 승격 권한 없음')
                expect(page.locator('#main-content')).to_contain_text('UNKNOWN')
            else:
                metric=page.get_by_role('link',name='정확한 구성',exact=False)
                if metric.count():
                    metric.first.click()
                    expect(page.locator('#main-content')).to_contain_text('정확한 구성 행')
                    disclosure=page.locator('details:has(> summary:has-text("정제된 원천 증거 펼치기"))')
                    if disclosure.count():
                        disclosure.first.locator('summary').click()
                        assert disclosure.first.get_attribute('open') is not None
                    assert_rendered_contract(page,width,theme)
        page.goto(operator_server+path)


def bounded_context(browser,origin,**kwargs):
    context=browser.new_context(service_workers='block',accept_downloads=True,**kwargs)
    violations=[]
    def route(request):
        if urlsplit(request.request.url)[:2]==urlsplit(origin)[:2]:
            request.continue_()
        else:
            violations.append(request.request.url)
            request.abort()
    context.route('**/*',route)
    return context,violations


@pytest.mark.parametrize('width,javascript',[(1280,True),(390,True),(320,True),(320,False)])
def test_native_all_navigation_exports_filters_and_ack(browser,operator_server,alert_web,width,javascript):
    from operator_fixtures import capture_sources,SECRET_SENTINEL
    _,_,sources,alerts,episode,_=alert_web
    baseline=capture_sources(sources)
    context,violations=bounded_context(browser,operator_server,viewport={'width':width,'height':900},
        java_script_enabled=javascript,color_scheme='dark')
    with context:
        page=context.new_page()
        page.set_default_timeout(5000)
        enter(page,operator_server)
        if not javascript:
            menu=page.locator('.navigation-disclosure > summary')
            menu.focus()
            page.keyboard.press('Space')
            assert page.locator('.navigation-disclosure').get_attribute('open') is None
            assert menu.get_attribute('aria-expanded') is None
            page.keyboard.press('Enter')
            expect(page.locator('#operator-navigation')).to_be_visible()
            paths=page.locator('#operator-navigation a').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))')
            for path in paths:
                page.locator('#operator-navigation a[href="'+path+'"]').click()
                expect(page.locator('#main-content h1')).to_be_visible()
                for link in page.locator('#operator-evidence a[href^="/records/"]').all():
                    destination=link.get_attribute('href')
                    page.goto(operator_server+destination)
                    expect(page.locator('#main-content h1')).to_be_visible()
                    page.goto(operator_server+path)
        page.goto(operator_server+'/orders')
        page.get_by_label('조회 기간',exact=True).select_option('7d')
        page.get_by_role('button',name='범위 적용',exact=True).click()
        expect(page.locator('#main-content')).to_contain_text('000660')
        assert 'period=7d' in page.url
        # Every currently AVAILABLE report family, real browser downloads, byte parsing.
        for family in ('daily','period','replay','backtest','shadow','soak'):
            page.goto(operator_server+'/reports')
            form=page.locator('form:has([name=family][value='+family+'])')
            if family=='soak':
                form.locator('[name=result_id]').fill('operator-campaign')
            form.get_by_role('button',name='보고서 생성',exact=True).click()
            expect(page.locator('#generated-report')).to_be_visible()
            for fmt in ('TXT','JSON','CSV'):
                with page.expect_download() as saved:
                    page.get_by_role('link',name=fmt+' 내려받기',exact=True).click()
                download=saved.value
                assert download.failure() is None and download.suggested_filename.endswith('.'+fmt.lower())
                content=Path(download.path()).read_bytes()
                assert content and SECRET_SENTINEL.encode() not in content
                if fmt=='JSON':
                    document=json.loads(content)
                    assert family in str(document) and 'selection' in str(document)
                    assert 'denominator' in str(document) and 'resource_id' in str(document)
                elif fmt=='CSV':
                    rows=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
                    assert rows and 'resource_id' in str(rows)
        page.goto(operator_server+'/alerts/'+episode.episode_id)
        page.get_by_label('대응 메모 (선택)',exact=True).fill('휴대폰으로 확인')
        page.get_by_role('button',name='읽음으로 기록',exact=True).click()
        expect(page.locator('#refresh-status')).to_contain_text('읽음으로 기록했습니다')
        assert alerts.get_incident(episode.episode_id).active
        assert alerts.list_acknowledgements(episode.episode_id)[0].note=='휴대폰으로 확인'
        page.goto(operator_server+'/')
        expect(page.locator('#main-content')).to_contain_text('동결 유지')
    assert not violations
    assert capture_sources(sources)==baseline


@pytest.mark.parametrize('theme',['light','dark'])
def test_keyboard_skip_menu_focus_local_scroll_and_200_percent_zoom(operator_page,operator_server,theme):
    page=operator_page
    page.set_viewport_size({'width':1280,'height':900})
    page.emulate_media(color_scheme=theme,reduced_motion='reduce')
    enter(page,operator_server)
    page.goto(operator_server+'/')
    page.keyboard.press('Tab')
    expect(page.get_by_role('link',name='본문으로 이동',exact=True)).to_be_focused()
    facts=page.evaluate(MEASURE)
    assert facts['focus']['width']=='2px' and facts['focus']['contrast']>=3
    page.keyboard.press('Enter')
    expect(page.locator('#main-content')).to_be_focused()
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.tagName')=='A'
    page.set_viewport_size({'width':390,'height':900})
    summary=page.locator('.navigation-disclosure > summary')
    summary.focus()
    page.keyboard.press('Space')
    expect(summary).to_have_attribute('aria-expanded','false')
    page.keyboard.press('Enter')
    expect(summary).to_have_attribute('aria-expanded','true')
    expect(page.locator('#operator-navigation')).to_be_visible()
    page.set_viewport_size({'width':1280,'height':900})
    page.evaluate("document.body.style.zoom='2'")
    assert page.evaluate("getComputedStyle(document.body).zoom")=='2'
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
    expect(page.locator('#main-content')).to_contain_text('000660')
    page.evaluate("document.body.style.zoom='1'")
    page.set_viewport_size({'width':320,'height':900})
    page.evaluate("""() => { for(const [key,value] of Object.entries({'--font-body':'32px',
      '--font-label':'28px','--font-heading':'40px','--font-display':'56px'}))
      document.documentElement.style.setProperty(key,value); }""")
    assert page.evaluate('getComputedStyle(document.body).fontSize')=='32px'
    assert_rendered_contract(page,320,theme)


def test_concurrent_pc_phone_independent_absolute_session_boundaries(browser,operator_server,alert_web):
    _,_,sources,_,_,_=alert_web
    pc,pc_violations=bounded_context(browser,operator_server,viewport={'width':1280,'height':900})
    phone,phone_violations=bounded_context(browser,operator_server,viewport={'width':390,'height':900},has_touch=True)
    with pc,phone:
        a,b=pc.new_page(),phone.new_page()
        a.clock.install(time=sources.clock())
        enter(a,operator_server,'/account')
        first=pc.cookies()[0]['value']
        sources.clock.advance(hours=1)
        b.clock.install(time=sources.clock())
        enter(b,operator_server,'/account')
        assert phone.cookies()[0]['value']!=first
        a.goto(operator_server+'/account')
        expect(a.locator('#main-content')).to_contain_text('operator-snapshot')
        sources.clock.advance(hours=11)
        a.goto(operator_server+'/account')
        expect(a.get_by_role('button',name='로그인',exact=True)).to_be_visible()
        b.goto(operator_server+'/account')
        expect(b.locator('#main-content')).to_contain_text('operator-snapshot')
        sources.clock.advance(hours=1)
        b.goto(operator_server+'/account')
        expect(b.get_by_role('button',name='로그인',exact=True)).to_be_visible()
    assert not pc_violations and not phone_violations


def test_saved_incomplete_zero_amounts_remain_unknown_and_historic_risk_visible(operator_page,operator_server,alert_web):
    import sqlite3
    from operator_fixtures import capture_sources
    _,_,sources,_,_,_=alert_web
    # Test-owned producer writes the new saved failure before the tested read.
    with sqlite3.connect(sources.paths['audit']) as conn:
        conn.execute("UPDATE portfolio_snapshots SET completeness='INCOMPLETE',reason_code='MISSING_PAGE',available_cash=0,total_evaluation=0")
    baseline=capture_sources(sources)
    page=operator_page
    page.set_viewport_size({'width':320,'height':900})
    enter(page,operator_server,'/account')
    expect(page.locator('#operator-evidence')).to_contain_text('UNKNOWN · 확인되지 않음')
    assert '0원' not in page.locator('#operator-evidence').inner_text()
    page.goto(operator_server+'/orders?period=today')
    expect(page.locator('#main-content')).to_contain_text('000660')
    expect(page.locator('#main-content')).to_contain_text('모든 날짜')
    assert capture_sources(sources)==baseline


def test_real_download_formula_text_is_safe_and_selection_denominators_match(operator_page,operator_server,alert_web):
    from test_reporting import _manifest
    from trading_bot.replay_evidence import ReplayOutcome,ReplayResult,ReplayVerification,build_replay_funnel
    from operator_fixtures import capture_sources
    _,_,sources,_,_,_=alert_web
    outcome=ReplayOutcome('saved-scenario','000660',1,'BUY',True,'FILLED','=SUM(1,1)',1000,1,'BUY',True,
        selected=True,buy_signaled=True,confidence_qualified=True,risk_qualified=True,validly_sized=True,order_eligible=True)
    result=ReplayResult(_manifest(),(outcome,),{},build_replay_funnel((outcome,)),ReplayVerification(True,()))
    sources.paths['replay'].write_bytes(result.normalized_bytes())
    baseline=capture_sources(sources)
    page=operator_page
    page.set_viewport_size({'width':320,'height':900})
    enter(page,operator_server,'/reports')
    page.locator('form:has([name=family][value=replay])').get_by_role('button',name='보고서 생성',exact=True).click()
    downloads={}
    for fmt in ('JSON','CSV'):
        with page.expect_download() as saved:
            page.get_by_role('link',name=fmt+' 내려받기',exact=True).click()
        downloads[fmt]=Path(saved.value.path()).read_text(encoding='utf-8-sig')
    structured=json.loads(downloads['JSON'])
    assert result.result_id in str(structured)
    assert 'numerator' in str(structured) and 'denominator' in str(structured)
    assert "'=SUM(1,1)" in downloads['CSV']
    assert not any(cell.lstrip().startswith('=') for row in csv.reader(io.StringIO(downloads['CSV'])) for cell in row)
    assert capture_sources(sources)==baseline


def test_bounded_synthetic_overview_review_screenshots(operator_page,operator_server,tmp_path):
    page=operator_page
    enter(page,operator_server)
    for width,theme in ((1280,'light'),(390,'dark'),(320,'light')):
        page.set_viewport_size({'width':width,'height':900})
        page.emulate_media(color_scheme=theme)
        page.goto(operator_server+'/')
        if width<1024:
            page.locator('.navigation-disclosure > summary').click()
        path=tmp_path/f'operator-overview-{width}-{theme}.png'
        page.screenshot(path=str(path))
        assert path.is_file()
        print('SYNTHETIC_REVIEW_SCREENSHOT='+str(path))
