import hashlib
import urllib2

from test_services import GET

from akara import pipeline

def test_pipeline_missing_stages():
    for stages in (None, [], ()):
        try:
            pipeline.register_pipeline("blah", stages=stages)
        except TypeError:
            pass
        else:
            raise AssertError("allowed missing stages: %r" % stages)

def test_flatten():
    result = list(pipeline._flatten_kwargs_values(dict(a=["1","2","3"])))
    assert result == [("a","1"), ("a","2"), ("a","3")], result
    result = list(pipeline._flatten_kwargs_values(dict(a=["1","2","3"], b="9")))
    result.sort()
    assert result == [("a","1"), ("a","2"), ("a","3"), ("b","9")], result

def test_stage_query_args():
    stage = pipeline.Stage("http://example.com", [("a", ["1", "2"]), ("b", "9")])
    assert stage.query_string == "a=1&a=2&b=9", stage.query_string

def test_stage_kwargs():
    stage = pipeline.Stage("http://example.com", a=["1", "2"], b="9")
    assert (stage.query_string == "a=1&a=2&b=9" or
            stage.query_string == "b=9&a=1&a=2"), stage.query_string
    
def test_stage_raw_query():
    stage = pipeline.Stage("http://example.com", query_string="=j")
    assert stage.query_string == "=j"

def test_stage_error_combinations():
    # Not allowed to mix inputs
    def t1():
        pipeline.Stage("http://example.com", [("a", "b")], query_string="=j")
    def t2():
        pipeline.Stage("http://example.com", [("a", "b")], a=3)
    def t3():
        pipeline.Stage("http://example.com", query_string="=j", a=3)

    for t in (t1, t2, t2):
        try:
            t()
        except TypeError:
            pass
        else:
            raise AssertionError("expected to fail")



def test_hash_encode():
    result = GET("hash_encode", data="This is a test")
    expected = hashlib.md5("secretThis is a test").digest().encode("base64")
    assert result == expected, (result, expected)

def test_hash_encode_rot13():
    result = GET("hash_encode_rot13", data="This is another test")
    expected = hashlib.md5("secretThis is another test").digest().encode("base64").encode("rot13")
    assert result == expected, (result, expected)

def test_get_hash():
    result = GET("get_hash")
    expected = hashlib.md5("Andrew").digest().encode("base64")
    assert result == expected, (result, expected)

def test_get_hash2():
    result = GET("get_hash", dict(text="Sara Marie"))
    expected = hashlib.md5("Sara Marie").digest().encode("base64")
    assert result == expected, (result, expected)

def test_broken_pipeline1():
    try:
        result = GET("broken_pipeline1")
        raise AssertionError("should not get here")
    except urllib2.HTTPError, err:
        assert err.code == 500
        msg = err.read()
        assert "Broken internal pipeline" in msg, msg

def test_broken_pipeline2():
    try:
        result = GET("broken_pipeline2", data="feed the pipeline")
        raise AssertionError("should not get here")
    except urllib2.HTTPError, err:
        assert err.code == 500, err.code
        msg = err.read()
        assert "Broken internal pipeline" in msg, msg

def test_registry_size():
    result = GET("test_count_registry")
    assert int(result) > 30, "What?! Did you remove elements from the registry?"
