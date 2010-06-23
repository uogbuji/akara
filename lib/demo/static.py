# -*- encoding: utf-8 -*-
'''Serve static files from the file system

Requires a configuration section, for example:

class static:
    akara_module = "akara.demo.static"
    paths = {"images": "/path/to/image/directory",
             "~me": "/home/directory/public_files"}

'''

import os
import stat
import mimetypes
from email.utils import formatdate
import warnings

from akara import registry

SERVICE_ID = 'http://purl.org/akara/services/demo/static'

class MediaHandler(object):

    __name__ = 'MediaHandler'

    def __init__(self, media_root):
        media_root = os.path.abspath(media_root)
        if not media_root.endswith(os.sep):
            media_root += os.sep
        self.media_root = media_root

    def __call__(self, environ, start_response):

        path_info = environ['PATH_INFO']
        if path_info[:1] == '/':
            path_info = path_info[1:]

        filename = os.path.join(self.media_root, path_info)
        # Simple security check.
        # Things like "con" on Windows will mess it up.
        filename = os.path.normpath(filename)
        if not filename.startswith(self.media_root):
            start_response('401 Unauthorized', [('Content-Type', 'text/plain')])
            return ["Path is outside of the served directory"]

        if not os.path.exists(filename):
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return ['Nothing matches the given URI']

        try:
            fp = open(filename, 'rb')
        except IOError:
            start_response('401 Unauthorized', [('Content-Type', 'text/plain')])
            return ['Permission denied']

        # This is a very simple implementation of conditional GET with
        # the Last-Modified header. It makes media files a bit speedier
        # because the files are only read off disk for the first request
        # (assuming the browser/client supports conditional GET).
        mtime = formatdate(os.stat(filename).st_mtime, usegmt=True)
        headers = [('Last-Modified', mtime)]
        if environ.get('HTTP_IF_MODIFIED_SINCE', None) == mtime:
            status = '304 Not Modified'
            output = ()
        else:
            status = '200 OK'
            mime_type = mimetypes.guess_type(filename)[0]
            if mime_type:
                headers.append(('Content-Type', mime_type))
            output = [fp.read()]
            fp.close()
        start_response(status, headers)
        return output

import akara
paths = akara.module_config(__name__).paths

for path, root in paths.items():
    handler = MediaHandler(root)
    registry.register_service(SERVICE_ID, path, handler)
