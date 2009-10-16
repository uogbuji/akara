from akara.services import method_dispatcher

@method_dispatcher("http://purl.org/spam", "vikings")
def vikings():
    """Sing the Viking song

    GET: [word=string] returns the song for that word
    POST: returns some other text
    """

@vikings.simple_method("GET", "text/plain")
def vikings_get(word):
    word = word[0]
    yield "%s, %s, %s, %s\n" % (word, word, word, word)
    yield "%s, %s, %s, %s\n" % (word, word, word, word)
    yield "%s-itty %s!\n" % (word, word)

@vikings.method("POST")
def vikings_post(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return "That was interesting.\n"
