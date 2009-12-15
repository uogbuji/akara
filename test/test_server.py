from server_support import server
import urllib2
from urllib2 import urlopen
from collections import defaultdict

import amara

# check that the servers restart after 10 calls
# (MaxRequestsPerServer = 5 * MaxServers = 5 means no more than 25 calls)

_legal_counts = set("0 1 2 3 4".split())
def test_restart():
    url = server() + "test_get_call_count"
    
    pid_counts = defaultdict(list)
    for i in range(50):
        result = urlopen(url).read()
        count, pid = result.split()
        pid_counts[pid].append(count)

    items = sorted(pid_counts.items())
    for pid, counts in items:
        print pid, counts

    print "NOTE: this is only valid for special configuration setups"
    for pid, counts in items:
        counts_set = set(counts)
        assert len(counts) == len(counts_set), repr(counts)
        for count in counts:
            assert count in _legal_counts, count

def test_index():
    url = server()
    xml = urlopen(url).read()
    print xml
    assert "This is an internal class" not in xml
    assert ("<path>test_echo_simple_get</path>"
            "<description>This echos a GET request, including the QUERY_STRING</description>") in xml
    assert "<path>test_multimethod</path><description>SHRDLU says 'QWERTY'</description>" in xml

def test_index_search():
    url = server() + "?service=http://example.com/test_echo"
    xml = urlopen(url).read()
    assert xml.startswith('''<?xml version="1.0" encoding="utf-8"?>
<services><service '''), repr(xml[:100])
    assert ('<service ident="http://example.com/test_echo">'
            '<path>test_echo_simple_get</path>'
            '<description>This echos a GET request, including the QUERY_STRING</description>'
            '</service>') in xml
    
    assert ('<service ident="http://example.com/test_echo">'
            '<path>test_echo_simple_get2</path>'
            '<description>Hi test_server.py!</description>'
            '</service>') in xml
    assert xml.count("<service ") == 2, xml.count("<service ")

def test_index_search_no_hits():
    url = server() + "?service=http://example.com/test_echo_werwrwerqwerqwerqwerqwerqwer"
    xml = urlopen(url).read()
    assert xml == ('<?xml version="1.0" encoding="utf-8"?>\n'
                   '<services/>'), repr(xml)

def test_404_error_message():
    url = server() + "this_does_not_exist/I_mean_it/Anybody_want_a_peanut?"
    try:
        urlopen(url)
        raise AssertionError("that URL should not be present")
    except urllib2.HTTPError, err:
        assert err.code == 404
        assert err.headers["Content-Type"] == "text/html", err.headers["Content-Type"]
        tree = amara.parse(err.fp, standalone=True)

def test_405_error_message():
    url = server()
    try:
        f = urlopen(url, "The server ignores this text")
        raise AssertionError("/ is not supposed to allow a POST")
    except urllib2.HTTPError, err:
        assert err.code == 405, err.code
        assert err.headers["Content-Type"] == "text/html", err.headers["Content-Type"]
        tree = amara.parse(err.fp, standalone=True)

def test_405_error_message_mega(n=100):
    import time
    t1=time.time()
    for i in range(n):
        test_405_error_message()
    t2=time.time()
    # This catches an error in the error handling code where I did
    # not parse in standalone mode, causing a 0.75s network load.
    if n / (t2-t1+0.00001) < 2:
        raise AssertionError("Should be able to handle more than 2 failure requests/seconds")

if __name__ == "__main__":
    def server():
        #return "http://192.168.2.101:8880/"
        return "http://localhost:8880/"
    test_405_error_message_mega(1000)
