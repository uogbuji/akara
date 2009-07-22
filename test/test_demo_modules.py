from server_support import server

from urllib2 import urlopen


# luckygoogle.pt
def test_luckygoogle():
    url = server() + "akara.luckygoogle?q=google"
    f = urlopen(url)
    s = f.read()
    assert s == "http://www.google.com/\n", repr(s)

# atomtools.py
def test_atom_json():
    import simplejson
    url = server() + "akara.atom.json?url=http://zepheira.com/feeds/news.atom"
    f = urlopen(url)
    results = simplejson.load(f)
    items = results["items"]
    for item in items:
        assert "title" in item

def test_webfeedjson():
    import simplejson
    url = server() + "akara.webfeed.json?url=http://feeds.delicious.com/v2/rss/recent%3Fmin=1%26count=15"
    f = urlopen(url)
    results = simplejson.load(f)
    print results

if __name__ == "__main__":
    raise SystemExit("Use nosetests")
