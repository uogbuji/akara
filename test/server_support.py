"""Support module to start a local Akara test server"""

import atexit
import os
from os.path import abspath, dirname
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib2

import python_support

######
module_dir = os.path.join(dirname(dirname(abspath(__file__))), "demo", "modules")
assert os.path.exists(module_dir), "no module directory?"

# All of the tests use a single server instance.
# This is started the first time it's needed.
# It is stopped during test shutdown.

def _override_server_uri():
    server = os.environ.get("AKARA_TEST_SERVER", None)
    if not server:
        return None
    assert "/" not in server
    return "http://" + server + "/"
    
SERVER_URI = _override_server_uri()
server_root = None
config_filename = None
server_pid = None

# Create a temporary directory structure for Akara.
# Needs a configuration .ini file and the logs subdirectory.
def create_server_dir(port):
    global server_root, config_filename
    
    server_root = tempfile.mkdtemp(prefix="akara_test_")
    config_filename = os.path.join(server_root, "akara_test.ini")

    f = open(config_filename, "w")
    f.write("""[global]
ServerRoot: %(server_root)s
ModuleDir: %(module_dir)s
Listen: localhost:%(port)s
""" % dict(server_root = server_root,
           module_dir = module_dir,
           port = port))
    f.close()

    os.mkdir(os.path.join(server_root, "logs"))

# Remove the temporary server configuration directory,
# if I created it
def remove_server_dir():
    global server_pid, server_root
    if server_pid is not None:
        # I created the server, I kill it
        os.kill(server_pid, signal.SIGTERM)
        server_pid = None

    if server_root is not None:
        print server_root
        #shutil.rmtree(server_root)
        server_root = None

atexit.register(remove_server_dir)

# Start a new Akara server in server mode.
def start_server():
    global server_pid

    port = python_support.find_unused_port()
    create_server_dir(port)
    args = [sys.executable, "-m", "akara.server",
            "--config-file", config_filename]
    result = subprocess.call(args)

    # Akara started, but it might have failed during startup.
    # Report errors by reading the error log
    if result != 0:
        f = open(os.path.join(server_root, "logs", "error.log"))
        err_text = f.read()
        raise AssertionError("Could not start %r:\n%s" % (args, err_text))

    # Akara started, but perhaps it didn't get that far.
    # Check that by fetching the pid from the pid log file.
    # However, the pid file is created after the process
    # detactes from the controlling process, so there's a
    # timing problem. (ticket #9). The file might not yet
    # exist, or not yet be populated with the pid information.
    # Try getting it a few times
    for i in range(10):
        try:
            f = open(os.path.join(server_root, "logs", "akara.pid"))
            line = f.readline()
            f.close()
            # Make sure it's an integer (I've seen it be a blank line)
            int(line)
        except (IOError, ValueError):
            if i == 9:
                raise
        else:
            break
        time.sleep(0.1)

    # Save the pid information now so the server will be shut down
    # if there are any problems.
    server_pid = int(line)

    # Check to see that the server process really exists.
    # (Is this overkill? Is this portable for Windows?)
    os.kill(server_pid, 0)  # Did Akara really start?

    check_that_server_is_available(port)

    return port

# It takes the server a little while to get started.
# In the worst case (trac #6), top-level import failures
# will loop forever, and the server won't hear requests.
def check_that_server_is_available(port):
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(5.0)
        try:
            urllib2.urlopen("http://localhost:%d/" % port).read()
        except urllib2.URLError, err:
            print "Current error log is:"
            f = open(os.path.join(server_root, "logs", "error.log"))
            err_text = f.read()
            print err_text
            raise
    finally:
        socket.setdefaulttimeout(old_timeout)

# Get the server URI prefix, like "http://localhost:8880/"
def server():
    global SERVER_URI
    if SERVER_URI is None:
        # No server specified and need to start my own
        port = start_server()
        SERVER_URI = "http://localhost:%d/" % port

    return SERVER_URI

