"""Parse the Akara config file (in .ini format) and get system settings from it

This is an internal module and should not be used by other libraries.

"""
import os
import logging
import inspect

class Error(Exception):
    pass

DEFAULT_SERVER_CONFIG_FILE = os.path.expanduser("~/.config/akara.conf")

class AkaraDefault:
    Listen = 8880
    ServerRoot = "~/.local/lib/akara"
    #"ServerPath": None
    #"InternalServerPath": None
    PidFile = "logs/akara.pid"

    MinSpareServers = 5
    MaxSpareServers = 10
    MaxServers = 150
    MaxRequestsPerServer = 10000

    ModuleDir = 'modules'
    ModuleCache = 'caches'
    ErrorLog = 'logs/error.log'
    AccessLog = 'logs/access.log'
    LogLevel = 'INFO'



_valid_log_levels = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARN": logging.WARN,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    }


log = logging.getLogger("akara.server")

def _add_akara_defaults(akara_namespace):
    # in-place modify the namespace
    for name, value in inspect.getmembers(AkaraDefault):
        if name.startswith("_"):
            continue
        if not hasattr(akara_namespace, name):
            setattr(akara_namespace, name, value)
    
def read_config(config_file=None):
    "Read an Akara configuration file and return the parsed settings"
    if config_file is None:
        config_file = DEFAULT_SERVER_CONFIG_FILE
    try:
        config = open(config_file).read()
    except IOError, err:
        raise Error("""\
Could not open Akara configuration file:
   %s
To set up the default configuration file and directories use "akara setup"\
""" % (err,))

    # XX better error reporting
    try:
        code = compile(config, config_file, "exec")
    except SyntaxError, err:
        raise Error("""\
Could not parse Akara configuration file:
   %s
because: %s""" % (config_file, err))
         
    namespaces = dict(__builtins__ = None, __name__ = "akara.conf")
    exec code in namespaces

    errmsg = None
    if "Akara" not in namespaces:
        raise Error("Configuration file missing required 'Akara' definition")

    _add_akara_defaults(namespaces["Akara"])
    settings = _extract_settings(namespaces["Akara"])
    return settings, namespaces

def _extract_settings(config):
    """Get parsed setting information from a config object

    This does sanity checking on the input (like that port numbers
    must be positive integers) and converts things into the
    appropriate data type (like integers).
    """
    # Some helper functions to get typed fields with good error reporting
    def get(key):
        value = getattr(config, key, None)
        if value is None:
            raise Error("Required 'Akara' configuration %r is missing" % (key,))
        return value
    
    def getstring(key):
        value = get(key)
        if not isinstance(value, basestring):
            raise Error("'Akara' configuration %r must be a string, not %r" %
                        (key, value))
        return value

    def getint(key):
        value = get(key)
        try:
            return int(value)
        except ValueError:
            raise Error("'Akara' configuration %r must be an integer, not %r" % 
                        (key, value))
        
    def getpositive(key):
        value = get(key)
        if value <= 0:
            raise Error(
                "'Akara' configuration %r must be a positive integer, not %r" %
                (key, value))
        return value

    def getnonnegative(key):
        value = getint(key)
        if value <= 0:
            raise Error(
                "'Akara' configuration %r must be a non-negative integer, not %r" %
                (key, value))
        return value


    settings = {}

    # The value for 'Listen' can be:
    #    <port> as in 8080
    # -or-
    #    <host>:<port> as in "localhost:8081"
    addr = get('Listen')
    if isinstance(addr, int):
        host, port = ("", addr)
    else:
        if ':' in addr:
            host, port_s = addr.rsplit(':', 1)
        else:
            host, port_s = '', addr
        try:
            port = int(port_s)
            if port <= 0:
                raise ValueError
        except ValueError:
            raise Error("Listen port must be a positive integer, not %r" % port_s)

    settings["server_address"] = (host, port)

    # Used to contract the full OpenSearch template to a given service.
    # If not present, use the Listen host and port.
    #  (And if the host isn't present, use 'localhost'. It's not a good
    #  default but I'm not going to do a FQDN lookup here since that has
    #  side effects. Basically, if you need the name right, then set it.)
    try:
        server_path = getstring('ServerPath')
    except Error:
        if port == 80:
            fmt = "http://%(host)s/"
        else:
            fmt = "http://%(host)s:%(port)s/"
        server_path = fmt % dict(host = (host or "localhost"), port = port)
        
    # Uses only when an Akara service wants to call another Akara service.
    # Needed for the (rare) cases when the listen server has a different
    # local name than the published server.
    try:
        internal_server_path = getstring('InternalServerPath')
    except Error:
        internal_server_path = server_path
        
    settings["server_path"] = server_path
    settings["internal_server_path"] = internal_server_path

    server_root = getstring('ServerRoot')
    server_root = os.path.expanduser(server_root)
    settings["server_root"] = os.path.abspath(server_root)

    pid_file = getstring('PidFile')
    settings["pid_file"] = os.path.join(server_root, pid_file)

    error_log = getstring('ErrorLog')
    settings["error_log"] = os.path.join(server_root, error_log)

    access_log = getstring('AccessLog')
    settings["access_log"] = os.path.join(server_root, access_log)

    module_dir = getstring("ModuleDir")
    settings["module_dir"] = os.path.join(server_root, module_dir)
    
    module_cache = getstring("ModuleCache")
    settings["module_cache"] = os.path.join(server_root, module_cache)

    log_level_orig = getstring('LogLevel')
    log_level_s = log_level_orig.upper()
    if log_level_s in _valid_log_levels:
        log_level = _valid_log_levels[log_level_s]
    else:
        raise Error(
            "global setting 'LogLevel' is %r but must be one of: %s" %
            (log_level_s, ", ".join(map(repr, _valid_log_levels))))
                    
    settings["log_level"] = log_level



    settings["max_servers"] = getpositive("MaxServers")
    settings["min_spare_servers"] = getnonnegative("MinSpareServers")
    settings["max_spare_servers"] = getnonnegative("MaxSpareServers")
    if settings["max_spare_servers"] < settings["min_spare_servers"]:
        raise Error("MaxSpareServers (%r) must be greater than MinSpareServers (%r)" %
                    (settings["max_spare_servers"], settings["min_spare_servers"]))
    settings["max_requests_per_server"] = getpositive("MaxRequestsPerServer")

    return settings
