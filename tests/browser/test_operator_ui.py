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
