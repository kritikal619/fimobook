"""Create a test browser with the same session-bound token as the real UI."""
from html.parser import HTMLParser


class _PageTokenParser(HTMLParser):
    token = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "fimobook-page-token":
            self.token = attrs.get("content")


def page_client(app, page="/squad_maker"):
    """Open the page before calling protected APIs; never disable the gate."""
    client = app.test_client()
    response = client.get(page)
    if response.status_code != 200:
        raise AssertionError(f"Token page {page} returned {response.status_code}")
    parser = _PageTokenParser()
    parser.feed(response.get_data(as_text=True))
    if not parser.token:
        raise AssertionError(f"Token page {page} did not provide a browser token")
    client.environ_base["HTTP_X_FIMOBOOK_PAGE_TOKEN"] = parser.token
    return client
