"""Provide caching of requests to Akara services.

The library implements a cache object that is wrapped around
an existing Akara service.   For example, suppose there is
an Akara service instance called http://myservices.com/bookprice
that returns the prices of books. A cache can be created as 
follows:

    from akara.caching import cache
    PRICE_CACHE = cache("http://myservices.com/bookprice")

The resulting PRICE_CACHE object then provides its own
API for issuing requests.  To issue a GET request, you would
do something like this:

    price = PRICE_CACHE.get(title="Python Essential Reference")

When this operation is performed, it is translated into a request
to the associated Akara mount point for the indicated service.
For example, if the "http://myservices.com/bookprice" service
has an Akara mountpoint of http://myhost/ak/bookprice.xml, then
a GET request for the following URL is issued:

    http://myhost/ak/bookprice.xml?title=Python%20Essential%20Reference

The actual mountpoint used is transparent.  Users specify a cache
according to a high-level service ID. Akara will figure out the
mount point internally using its registry or some other means.

Initial implementation:

The object returned by PRICE_CACHE.get() emulates that returned
by urllib2.urlopen().   That is, it is a file-like object that
can be read to obtain content.  The .info() method returns
information about returned HTTP headers.   If any errors occur
(e.g., 404), it results in an exception just like urllib2.urlopen().

The cache does not record HTTP errors.  Only the results of 
successful requests (200 OK) are stored.
"""

import urllib, urllib2
import os
import shutil
import sys
import base64
import hashlib
import cPickle as pickle
import time

from akara import registry
from akara import global_config

# File object returned to clients on cache hit.  A real file, but with an info() method
# to mimic that operation on file-like objects returned by urlopen().

class CacheFile(file):
    def __init__(self,*args, **kwargs):
        file.__init__(self,*args,**kwargs)
        self.headers = None
        self.code = 200
        self.url = None
        self.msg = "OK"
    def getcode(self):
        return self.code
    def geturl(self):
        return self.url
    def info(self):
        return self.headers

# Utility function to remove the oldest entry from a cache directory.
# Look at the modification dates for metadata files
def remove_oldest(cachedir):
    files = (name for name in os.listdir(cachedir) if name.endswith(".p"))
    paths = (os.path.join(cachedir,name) for name in files)
    time_and_paths = ((os.path.getmtime(path),path) for path in paths)
    oldest_time, path = min(time_and_paths)
    
    # Remove the oldest entry
    os.remove(path)
    
class cache(object):
    def __init__(self,ident,maxentries=65536,expires=15*60,opener=None):
        """Create a cache for another Akara service.

           ident is the Akara service ID
           maxentries is the maximum number of cache entries (approximate)
           expires is the time in seconds after which entries expire
           opener is an alternative URL opener.  By default urllib2.urlopen is used.
        """

        self.ident = ident
        if opener is None:
            opener = urllib2.urlopen
        self.opener = opener
        self.maxentries = maxentries
        self.expires = expires
        self.maxperdirectory = maxentries / 256
        self.serv = None
        self.initialized = False

    # Internal method that locates the Akara service description and sets up a
    # base-URL for making requests.   This can not be done in __init__() since
    # not all Akara services have been initialized at the same __init__() executes.
    # Instead, it has to be done lazily after all services are up and running.
    # In this implementation, the _find_service() method gets invoked upon the
    # first use of the cache
 
    def _find_service(self):
        self.serv = registry.get_a_service_by_id(self.ident)
        if not self.serv:
            raise KeyError("Nothing known about service %s" % ident)
#        print >>sys.stderr,"CACHE: %s at %s\n" % (self.ident, self.serv.path)

        hostname,port = global_config.server_address
        if not hostname:
            hostname = "localhost"
        self.baseurl = "http://%s:%d/%s" % (hostname, port, self.serv.path)
#        print >>sys.stderr,"CACHE: %s\n" % self.baseurl

    # Method that makes the cache directory if it doesn't yet exist
    def _make_cache(self):

        # Make sure the cache directory exists
        if not os.path.exists(global_config.module_cache):
            try:
                os.mkdir(global_config.module_cache)
            except OSError:
                pass    # Might be a race condition in creating.  Ignore errors, but follow up with an assert
            assert os.path.exists(global_config.module_cache),"%s directory can't be created" % (global_config.module_cache)

        self.cachedir = os.path.join(global_config.module_cache,self.serv.path)
        if not os.path.exists(self.cachedir):
            try:
                os.mkdir(self.cachedir)
            except OSError:
                # This exception handler is here to avoid a possible race-condition in startup.
                # Multiple server instances might enter here at the same time and try to create directory
                pass
            assert os.path.exists(self.cachedir), "Failed to make module cache directory %s" % self.cachedir

    # Method that initializes the cache if needed
    def _init_cache(self):
        self._find_service()
        self._make_cache()
        self.initialized = True

    def get(self,**kwargs):
        """Make a cached GET request to an Akara service.  If a result can be
           found in the cache, it is returned.  Otherwise, a GET request is issued
           to the service using urllib2.urlopen().  The result of this operation 
           mimics the file-like object returned by urlopen().   Reading from the file
           will return raw data.  Invoking the .info() method will return HTTP
           metadata about the request."""

        # Check to see if the cache has been initialized or not.  This has to be done here since
        # it is currently not possible to fully initialize the cache in __init__().
        if not self.initialized:
            self._init_cache()

        # This is a sanity check.  If the cache is gone, might have to rebuild it
        if not os.path.exists(self.cachedir):
            self._make_cache()

        #  Make a canonical query string from the arguments (guaranteed
        #  to be the same even if the keyword argumenst are specified in
        #  in an arbitrary order)
        #
        
        query = "&".join(name+"="+urllib.quote(str(value)) for name,value in sorted(kwargs.items()))

        # Take the query string and make a SHA hash key pair out of it.  The general idea here
        # is to come up with an identifier that has a reasonable number of bits, but which is extremely
        # unlikely to collide with other identifiers.  It would be extremely unlikely that the query
        # would have a collision with other entries
        
        shadigest = hashlib.sha1()
        shadigest.update(query)

        # Create a unique cache identifier from the digest.

        identifier = shadigest.hexdigest()

        # Caching operation.  The identifier is split into 2 parts.  The first byte is turned
        # into two hex digits which specify a cache directory.  The remaining bytes are turned
        # into a 47-character filename.
        # specify a cache directory.  The remaining digits specify a filename.  We do this
        # to avoid putting too many files into one big directory (which slows down filesystem operations

        subdir = identifier[:2]
        filename = identifier[2:]

        # Check for the existence of a cache subdirectory.  Make it if neeeded
        cache_subdir = os.path.join(self.cachedir,subdir)
        if not os.path.exists(cache_subdir):
            # Make the cache subdirectory if it doesn't exist
            try:
                os.mkdir(cache_subdir)
            except OSError:
                pass    # Here for possible race condition
            assert os.path.exists(cache_subdir), "Failed to make directory %s" % cache_subdir
            
        # Check for existence of cache file
        cache_file= os.path.join(cache_subdir,filename+".p")
        if os.path.exists(cache_file):
            # A cache hit. Load the metadata file to get the cache information and return it.
            f = CacheFile(cache_file,"rb")
            metaquery,timestamp,url,headers = pickle.load(f)

            # Check to make sure the query string exactly matches the meta data
            # and that the cache data is not too old
            if metaquery == query and (timestamp + self.expires > time.time()):
                # A cache hit and the query matches.  Just return the file we opened.
                # the file pointer should be set to imemdiately after the pickled
                # metadata at the front
                f.headers = headers
                f.url = url
                return f

            # There was a cache hit, but the cache metadata is for a different query (a collision)
            # or the timestamp is out of date.   We're going to remove the cache file and 
            # proceed as if there was a cache miss
            try:
                os.remove(cache_file)
            except OSError:
                pass   # Ignore.  If the files don't exist, who cares?
            
        # Cache miss
        # On a miss, a GET request is issued using the cache opener object
        # (by default, urllib2.urlopen).  Any HTTP exceptions are left unhandled
        # for clients to deal with if they want (HTTP errors are not cached)

        # Before adding a new cache entry. Check the number of entries in the cache subdirectory.
        # If there are too many entries, remove the oldest entry to make room.
        if len(os.listdir(cache_subdir)) >= self.maxperdirectory:
            remove_oldest(cache_subdir)

        # Make an akara request
        url = self.baseurl + "?" + query
        u = self.opener(url)
        
        # If successful, we'll make it here.  Read data from u and store in the cache
        # This is done by initially creating a file with a different filename, fully
        # populating it, and then renaming it to the correct cache file when done.
        cache_tempfile = cache_file + ".%d" % os.getpid()
        f = open(cache_tempfile,"wb")
        pickle.dump((query,time.time(),url,u.info()),f,-1)

        # Write content into the file
        while True:
            chunk = u.read(65536)
            if not chunk: break
            f.write(chunk)
        f.close()

        # Rename the file, open, and return
        shutil.move(cache_tempfile, cache_file)

        # Return a file-like object back to the client
        f = CacheFile(cache_file,"rb")
        metaquery,timestamp,f.url,f.headers = pickle.load(f)
        return f





                
                
                
            

        


        



        

        
        

        
        
        
        




        



