"""Navigation, the exec action set, and page snapshots."""

import pytest

from conftest import eventually


@pytest.fixture
def page(client, ctx, site):
    """A context already sitting on the test page."""
    status, body = client.goto(ctx["id"], f"{site}/index.html")
    assert status == 200, body
    return ctx["id"]


def read(client, ctx_id, element_id):
    status, body = client.exec(
        ctx_id, action="evaluate",
        script=f"document.getElementById('{element_id}').textContent")
    assert status == 200, body
    return body["result"]


def test_goto_reports_url_and_title(client, ctx, site):
    status, body = client.goto(ctx["id"], f"{site}/index.html")
    assert status == 200
    assert body["url"] == f"{site}/index.html"
    assert body["title"] == "Clawsome Test Page"


def test_click_follows_the_link(client, page, site):
    status, body = client.exec(page, action="click", selector="#more-link")
    assert status == 200
    assert body["action"] == "click"
    status, body = client.exec(page, action="evaluate", script="document.title")
    assert body["result"] == "Second Page"


def test_type_and_press(client, page):
    assert client.exec(page, action="type", selector="#search", value="hello")[0] == 200
    status, body = client.exec(page, action="press", selector="#search", value="Enter")
    assert status == 200
    # The page's own keydown handler proves the key really arrived.
    assert read(client, page, "pressed") == "key:Enter"


def test_hover_fires_the_pages_handler(client, page):
    assert client.exec(page, action="hover", selector="#hover-me")[0] == 200
    assert read(client, page, "hovered") == "hovered"


def test_select_option(client, page):
    status, _ = client.exec(page, action="select", selector="#choice", value="Beta")
    assert status == 200
    status, body = client.exec(
        page, action="evaluate", script="document.getElementById('choice').value")
    assert body["result"] == "Beta"


def test_wait_for_an_element(client, page):
    assert client.exec(page, action="wait", selector="#bottom")[0] == 200


@pytest.mark.parametrize(
    "value,expected",
    [("bottom", lambda y: y > 1000), ("top", lambda y: y == 0), ("500", lambda y: y == 500)],
)
def test_scroll_by_value(client, page, value, expected):
    status, body = client.exec(page, action="scroll", value=value)
    assert status == 200, body
    assert expected(body["position"]["y"]), body["position"]


def test_scroll_to_a_selector(client, page):
    status, body = client.exec(page, action="scroll", selector="#bottom")
    assert status == 200
    assert body["position"]["y"] > 1000


def test_scroll_rejects_a_nonsense_value(client, page):
    assert client.exec(page, action="scroll", value="sideways")[0] == 400


def test_press_requires_a_key(client, page):
    assert client.exec(page, action="press")[0] == 400


def test_back_and_reload(client, page, site):
    client.exec(page, action="click", selector="#more-link")
    status, body = client.exec(page, action="back")
    assert status == 200
    assert body["url"] == f"{site}/index.html"
    assert client.exec(page, action="reload")[0] == 200


def test_a_new_tab_is_adopted(client, page):
    """A target=_blank click should move the context onto the new tab.

    The browser reports the new tab a little after the click returns (~20ms
    measured), so this polls rather than assuming the very next call sees it.
    """
    assert client.exec(page, action="click", selector="#new-tab")[0] == 200
    title = eventually(
        lambda: client.exec(page, action="evaluate", script="document.title")[1]["result"],
        "Second Page")
    assert title == "Second Page"


def test_closing_an_adopted_tab_falls_back(client, page):
    client.exec(page, action="click", selector="#new-tab")
    eventually(
        lambda: client.exec(page, action="evaluate", script="document.title")[1]["result"],
        "Second Page")
    client.exec(page, action="evaluate", script="window.close()")
    title = eventually(
        lambda: client.exec(page, action="evaluate", script="document.title")[1]["result"],
        "Clawsome Test Page")
    assert title == "Clawsome Test Page"


def test_unknown_action_is_rejected(client, page):
    status, body = client.exec(page, action="not-a-real-action")
    assert status == 400
    assert "Unknown action" in str(body)


def test_snapshot_describes_the_page(client, page, site):
    status, snap = client.get(f"/api/contexts/{page}/snapshot")
    assert status == 200
    assert snap["url"] == f"{site}/index.html"
    assert snap["title"] == "Clawsome Test Page"
    assert "Some visible text" in snap["text"]

    by_selector = {e["selector"]: e for e in snap["elements"]}
    assert by_selector["#more-link"]["label"] == "More info"
    assert by_selector["#go"]["label"] == "Go"
    assert by_selector["#search"]["label"] == "Search..."
    # The selected option, not every option's text.
    assert by_selector["#choice"]["label"] == "Alpha"
    # Hidden elements are excluded.
    assert "#hidden-link" not in by_selector


def test_a_snapshot_selector_is_usable(client, page):
    """The whole point of snapshot: its selectors work in a follow-up action."""
    _, snap = client.get(f"/api/contexts/{page}/snapshot")
    link = next(e for e in snap["elements"] if e["label"] == "More info")
    assert client.exec(page, action="click", selector=link["selector"])[0] == 200
    status, body = client.exec(page, action="evaluate", script="document.title")
    assert body["result"] == "Second Page"
