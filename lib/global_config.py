"""
global_config holds the values of the Akara configuration parameters
from the [global] section of the configuration file.  The parameters
have the same names as those used in the settings parameter created
by the read_config.py.

Common configuration variables include:

server_address         : (host,port) of the Akara server
server_path            : public URL to the top-level of Akara
internal_server_path   : internal URL to the top-level of Akara
server_root            : Akara root directory (e.g., ~/.local/lib/akara)
pid_file               : Location of the PID file
error_log              : Filename of the Akara error log
access_log             : Filename of the Akara access log
module_dir             : Akara module directory
module_cache           : Module cache directory
log_level              : Logging level
max_servers            : Maximum number of servers
min_spare_servers      : Min spare servers
max_spare_servers      : Max spare servers
max_requests_per_server: Max requests per server

The primary purpose of this module is to make configuration parameters
available to various library modules that make up the Akara core. 
"""

# Initially this module is defined as empty.   It is populated by the
# akara.run module which reads the global config file and obtains the
# values of the various configuration paramaters




