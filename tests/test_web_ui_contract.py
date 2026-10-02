"""Pure saved-DTO rendering contracts; product browser proof belongs to 14-12."""
from pathlib import Path
import re

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
    assert page.header.select_one('summary[aria-controls="operator-navigation"]')
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


@pytest.mark.parametrize('url', ['/records/audit/orders%3A1?back=%2Forders%3Fperiod%3D7d',
                                '/evidence/portfolio/holdings%3Aoperator-snapshot%3A005930'])
def test_macro_canonical_encoded_saved_record_links(url):
    page = macro('{{ ui.link(url) }}', url=url)
    assert page.a['href'] == url


@pytest.mark.parametrize('url', ['//evil.test', '/records/audit/..%2Fsecret', '/evidence/audit/%252e%252e',
                                '/records/audit/%00', '/records/audit/%0a', '/evidence/audit/%5csecret',
                                '/records/audit/%2F%2Fevil.test', '/records/audit/../secret',
                                '/orders:evil', 'https://evil.test', '/records/audit/one\\two'])
def test_macro_canonical_links_reject_encoded_escape_and_traversal(url):
    assert not macro('{{ ui.link(url) }}', url=url).a


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
    assert sum(len(x.text.strip()) for x in bounded.select("pre, dt")) <= 16384


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


def css_text():
    path = ROOT / "trading_bot/static/operator.css"
    assert path.exists(), "approved native stylesheet must exist"
    return path.read_text()


def test_tokens_exact_approved_spacing_typography_and_dimensions():
    css = css_text()
    tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css))
    for name, value in {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32,
                        "2xl": 48, "3xl": 64}.items():
        assert tokens[f"--space-{name}"] == f"{value}px"
    for name, value in {"body": 16, "label": 14, "heading": 20, "display": 28}.items():
        assert tokens[f"--font-{name}"] == f"{value}px"
    for name, value in {"sidebar-width": "240px", "header-height": "64px",
                        "content-max": "1440px", "viewport-min": "320px",
                        "target-min": "44px", "row-min": "56px",
                        "radius-card": "8px", "radius-control": "4px"}.items():
        assert tokens[f"--{name}"] == value
    assert set(re.findall(r"font-weight:\s*(\d+)", css)) <= {"400", "600"}
    assert "system-ui" in css and '"Apple SD Gothic Neo"' in css and '"Malgun Gothic"' in css


def test_theme_exact_approved_light_dark_and_semantic_pairs():
    css = css_text()
    light, dark = css.split("@media (prefers-color-scheme: dark)", 1)
    palettes = [
        {"background": "#F8FAFC", "surface": "#FFFFFF", "accent": "#1D4ED8",
         "destructive": "#B91C1C", "text": "#0F172A", "muted": "#475569",
         "divider": "#CBD5E1", "control-border": "#64748B", "accent-foreground": "#FFFFFF",
         "info-text": "#1D4ED8", "info-bg": "#EFF6FF", "warning-text": "#92400E",
         "warning-bg": "#FFFBEB", "critical-text": "#B91C1C", "critical-bg": "#FEF2F2",
         "recovery-text": "#166534", "recovery-bg": "#F0FDF4"},
        {"background": "#0B1220", "surface": "#172033", "accent": "#93C5FD",
         "destructive": "#FCA5A5", "text": "#F1F5F9", "muted": "#CBD5E1",
         "divider": "#334155", "control-border": "#94A3B8", "accent-foreground": "#0B1220",
         "info-text": "#93C5FD", "info-bg": "#172554", "warning-text": "#FDE68A",
         "warning-bg": "#332B12", "critical-text": "#FCA5A5", "critical-bg": "#3F151C",
         "recovery-text": "#86EFAC", "recovery-bg": "#122C1C"},
    ]
    for section, palette in zip((light, dark), palettes):
        tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", section))
        assert {name: tokens[f"--{name}"] for name in palette} == palette
    assert "color-scheme: light dark" in css
    assert not any(x in css for x in ("@import", "https://", "@font-face", "data-theme", "opacity:", "gradient", "box-shadow"))


def test_responsive_focus_numeric_scroll_and_motion_contract():
    css = css_text()
    assert "@media (min-width: 1024px)" in css
    assert "@media (min-width: 768px) and (max-width: 1023px)" in css
    assert "@media (max-width: 767px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    for fact in ("font-variant-numeric: tabular-nums", "text-align: right",
                 "overflow-x: auto", ":focus-visible", "outline: 2px solid var(--accent)",
                 "outline-offset: 4px", "scroll-margin", "scroll-padding",
                 "overflow-wrap: anywhere", "text-decoration: underline",
                 "transition: none", "animation: none"):
        assert fact in css
    assert re.search(r"\.routine-table\s*\{\s*display:\s*none", css)
    assert re.search(r"\.record-cards\s*\{\s*display:\s*grid", css)
