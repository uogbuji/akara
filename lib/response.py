"""Information for the outgoing response

  code - the HTTP response code (default is "200 Ok")
  headers - a list of key/value pairs used for the WSGI start_response

"""

code = None
headers = []

def add_header(key, value):
    """Helper function to append (key, value) to the list of response headers"""
    headers.append( (key, value) )

# Eventually add cookie support?
