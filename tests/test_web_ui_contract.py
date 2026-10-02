"""Pure saved-DTO rendering contracts; product browser proof belongs to 14-12."""
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "trading_bot/templates"
NAVIGATION = {
    "운영 개요": [("/", "안전 개요"), ("/alerts", "알림"), ("/workers", "작업 상태")],
    "계좌·보유": [("/account", "계좌 요약"), ("/holdings", "보유 종목")],
    "판단·주문": [("/candidates", "선별 후보"), ("/decisions", "LLM 판단"),
              ("/orders", "주문"), ("/fills", "체결"), ("/runs", "실행 이력")],
    "검증·보고": [("/reports", "보고서"), ("/validation/replay", "Replay"),
              ("/validation/backtest", "백테스트"), ("/validation/shadow", "LLM Shadow"),
              ("/validation/soak", "모의투자 Soak"),
              ("/validation/calibration", "위험 보정"), ("/validation/readiness", "준비도")],
}


def environment():
    return Environment(loader=FileSystemLoader(TEMPLATES),
                       autoescape=select_autoescape(default_for_string=True))


def shell(**facts):
    return BeautifulSoup(environment().get_template("operator/base.html").render(
        title="안전 개요", current_path="/", **facts), "html.parser")


def macro(expression, **facts):
    return BeautifulSoup(environment().from_string(
        '{% import "operator/macros.html" as ui %}' + expression
    ).render(**facts), "html.parser")


def test_shell_semantic_landmarks_and_progressive_regions():
    page = shell()
    assert page.html["lang"] == "ko"
    assert len(page.select("h1")) == 1
    assert page.select_one('a[href="#main-content"]').text == "본문으로 이동"
    assert page.header and page.main and page.main["id"] == "main-content"
    assert page.select_one('[role="status"][aria-live="polite"]')
    assert page.select_one('[role="alert"]')
    assert page.select_one('form[method="get"] button').text.strip() == "저장 증거 새로고침"
    assert "새 시세 수집이나 거래 실행을 시작하지 않습니다." in page.text
    assert "UNKNOWN" in page.select_one(".target-badge").text


@pytest.mark.parametrize("path", [p for group in NAVIGATION.values() for p, _ in group])
def test_navigation_all_routes_and_current_marker(path):
    page = BeautifulSoup(environment().get_template("operator/base.html").render(
        title="검증", current_path=path), "html.parser")
    nav = page.select_one('#operator-navigation')
    assert [(x["href"], x.text.strip()) for x in nav.select("a")] == [
        pair for group in NAVIGATION.values() for pair in group]
    assert [x.text.strip() for x in nav.select("h2")] == list(NAVIGATION)
    assert [x["href"] for x in nav.select('[aria-current="page"]')] == [path]
    disclosure = page.select_one("details.navigation-disclosure")
    assert disclosure.summary["aria-controls"] == nav["id"]
    assert disclosure.summary["aria-expanded"] == "true"
    assert disclosure.has_attr("open")  # native disclosure works without JavaScript


def test_shell_blocks_preserve_mobile_evidence_and_action_affordances():
    env = environment()
    rendered = env.from_string('''{% extends "operator/base.html" %}
      {% block actions %}<button>보고서 생성</button><button>읽음으로 기록</button>{% endblock %}
      {% block evidence %}{{ ui.evidence_details(evidence) }}{% endblock %}''').render(
        title="보고서", current_path="/reports", evidence={"snapshot_id": "saved-1"})
    page = BeautifulSoup(rendered, "html.parser")
    assert "보고서 생성" in page.main.text and "읽음으로 기록" in page.main.text
    assert page.select_one("main details pre").text.strip() == "saved-1"
    assert "정제된 원천 증거 펼치기" in page.text


def test_macro_source_separates_query_observation_completeness_and_unknown_amount():
    page = macro('{{ ui.source_metadata(source) }}{{ ui.amount(value, "원") }}',
                 source={"resource_id": "synthetic", "record_id": "saved-1",
                         "observed_at": "2026-10-01 10:00:00 KST", "age": "1일",
                         "queried_at": "2026-10-02 10:00:00 KST",
                         "freshness": "STALE", "completeness": "INCOMPLETE",
                         "query_status": "FAILED"}, value=None)
    for value in ("원천 관측", "관측 경과", "화면 조회", "1일", "INCOMPLETE", "조회 실패",
                  "UNKNOWN · 확인되지 않음", "합계는 UNKNOWN"):
        assert value in page.text
    assert "0원" not in page.text
    known = macro('{{ ui.amount(value, "원") }}', value="1,234,567")
    assert known.text.strip() == "1,234,567원"


@pytest.mark.parametrize("state", ["INFO", "WARNING", "CRITICAL", "UNKNOWN", "INCOMPLETE", "PASS"])
def test_macro_status_has_visible_text_and_hidden_local_icon(state):
    page = macro('{{ ui.badge(state) }}', state=state)
    assert state in page.text
    assert page.svg["aria-hidden"] == "true"
    assert not page.select("img, script")


def test_macro_table_and_mobile_cards_share_facts_and_safe_detail_links():
    page = macro('{{ ui.records_table("보유", columns, rows, "holdings-table") }}',
                 columns=[{"key": "ticker", "label": "종목"},
                          {"key": "quantity", "label": "수량", "numeric": True}],
                 rows=[{"id": "holding-1", "ticker": "000660", "quantity": "123주",
                        "detail_url": "/holdings/holding-1"}])
    assert page.table.caption.text == "보유"
    assert all(th["scope"] == "col" for th in page.select("thead th"))
    container = page.select_one('.table-scroll[role="region"][tabindex="0"]')
    assert container["aria-labelledby"] == "holdings-table-caption"
    assert "000660" in page.table.text and "000660" in page.select_one(".record-cards").text
    assert "수량" in page.select_one(".record-cards dt:nth-of-type(2)").text
    assert len(page.select('a[href="/holdings/holding-1"]')) == 2


def test_macro_filter_pagination_and_evidence_bounds():
    page = macro('{{ ui.period_filter("/runs", "today", "mock") }}'
                 '{{ ui.pagination(2, none, "/runs?page=1", "/runs?page=3") }}'
                 '{{ ui.evidence_details(evidence, true) }}', evidence={"reason": "x" * 5000})
    assert page.form["method"] == "get" and page.form["action"] == "/runs"
    assert all(x in page.text for x in ("오늘", "최근 7일", "최근 30일", "기간 지정", "총건수 UNKNOWN"))
    assert page.select_one("label[for=period]")
    assert len(page.pre.text.strip()) == 4096
    assert "표시 한도에 도달했습니다." in page.text
    bounded = macro('{{ ui.evidence_details(evidence) }}', evidence={str(i): "y" * 4096 for i in range(8)})
    assert sum(len(x.text.strip()) for x in bounded.select("pre")) <= 16384


@pytest.mark.parametrize("attack", ['<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
                                    '\" autofocus onfocus=alert(1) x=\"'])
def test_escape_untrusted_shell_and_macro_facts(attack):
    page = shell(operator_name=attack, scope=attack, source={"resource_id": attack})
    evidence = macro('{{ ui.evidence_details(evidence) }}{{ ui.badge("UNKNOWN", label) }}',
                     evidence={"reason": attack}, label=attack)
    assert not page.select("script, img, [onfocus], [onerror]")
    assert not evidence.select("script, img, [onfocus], [onerror]")
    assert attack in page.text and attack in evidence.text


@pytest.mark.parametrize("url", ["javascript:alert(1)", "//evil.test", "/\\evil.test",
                                 "https://evil.test", "/orders/../execute", "/orders/execute:now"])
def test_escape_macro_rejects_source_driven_navigation(url):
    page = macro('{{ ui.link(url, "상세 보기") }}', url=url)
    assert not page.select("a[href]")
    assert "원천 연결을 확인할 수 없습니다." in page.text
