from __future__ import with_statement

# Test the underlying code for the Akara server process.
# (Does not start a running server process.)

import sys
import os
import tempfile
import shutil
from cStringIO import StringIO
import contextlib
import ConfigParser

from akara import server
from akara.server import logger, run

argv0 = sys.argv[0]

def _get_log(server_root):
    return open(os.path.join(server_root, "logs", "error.log")).read()

def test_process_default():
    process = run._create_process([argv0])
    assert process.ident == 'akara'
    assert process.config_file.startswith(os.path.expanduser("~"))
    # Check that it's at the default level
    assert process.log_level == logger.LOG_WARN

def test_process_debug():
    process = run._create_process([argv0, "-X"])
    assert process.log_level == logger.LOG_DEBUG


# The config reader has side-effects. It does a FQDN lookup and writes to a log file.
@contextlib.contextmanager
def config_tempdir():
    old_sys_stderr = sys.stderr
    old_sys_stdout = sys.stdout
    server_root = tempfile.mkdtemp(prefix="test_akara_server_config")
    os.mkdir(os.path.join(server_root, "logs"))
    try:
        yield server_root
    finally:
        # Restore any changes to sys.{stdout,stderr}
        # (Might be done as part of process.read_config() )
        sys.stdout = old_sys_stdout
        sys.stderr = old_sys_stderr
        shutil.rmtree(server_root)

@contextlib.contextmanager
def capturing_stderr(filehandle):
    old_sys_stderr = sys.stderr
    sys.stderr = filehandle
    try:
        yield
    finally:
        sys.stderr = old_sys_stderr

def test_process_missing_config():
    with config_tempdir() as server_root:
        stderr = StringIO()
        with capturing_stderr(stderr):
            process = run._create_process([argv0, "-f", "/dev/null/does/not/exist", "-X"])
            try:
                process.read_config()
                raise AssertionError("Why didn't that fail?")
            except SystemExit:
                # ignore the SystemExit because no port was specified
                pass
        msg = stderr.getvalue()
        assert "does/not/exist" in msg, msg
        assert "Missing required 'Listen' setting" in msg, msg


def write_config(server_root, params):
    filename = os.path.join(server_root, "akara.ini")
    config = ConfigParser.ConfigParser()
    config.add_section("global")
    config.set("global", "ServerRoot", server_root)
    for k, v in params.items():
        config.set("global", k, v)
    f = open(filename, "w")
    config.write(f)
    f.close()
    return filename

def test_process_host():
    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen=":80"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 80)

        # Also check a few of the other variables
        assert process.server_root == server_root, process.server_root
        assert process.pid_file.startswith(server_root), process.pid_file
        assert process.error_log.startswith(server_root), process.error_log
        


    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen=":810"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 810)

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="localhost:8765"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("localhost", 8765)

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 1234)



def test_process_no_error_log():
    stderr = StringIO()
    with capturing_stderr(stderr):
        with config_tempdir() as server_root:
            config_filename = write_config(server_root, dict(
                    Listen="1234", ErrorLog="/dev/null/does/not/exist"))
            process = run._create_process([argv0, "-f", config_filename])
            try:
                process.read_config()
                raise AssertionError("but there was no error log!")
            except SystemExit:
                pass
    msg = stderr.getvalue()
    assert "Could not open error log file"  in msg, msg
    assert "/does/not/exist" in msg, msg


def test_process_log_levels():
    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="debug",
                                                         ErrorLog = "spam.log"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        process.log.debug("Spam!")
        content = open(os.path.join(server_root, "spam.log")).read()
        assert "Spam!" in content, content


    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="info",
                                                         ErrorLog = "spam.log"))
        process = run._create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.debug == False
        process.log.debug("Spam!")
        content = open(os.path.join(server_root, "spam.log")).read()
        assert "Spam!" not in content, content

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="info",
                                                         ErrorLog = "spam.log"))
        process = run._create_process([argv0, "-f", config_filename, "-X"])  # Added -X
        # -X forces the level to debug and sends messages to stderr
        stderr = StringIO()
        with capturing_stderr(stderr):
            process.read_config()
            assert process.debug == True
            process.log.debug("Spam!")
        content = stderr.getvalue()
        assert "Spam!" in content, content # Should have debug level enabled


def test_process_bad_log_level():
    stderr = StringIO()
    with capturing_stderr(stderr):
        with config_tempdir() as server_root:
            config_filename = write_config(server_root, dict(Listen="1234", LogLevel="timber!",
                                                             ErrorLog = "spam.log"))
            process = run._create_process([argv0, "-f", config_filename])
            try:
                process.read_config()
                raise AssertionError("Did not catch the bad log level")
            except SystemExit:
                pass
    msg = stderr.getvalue()
    assert "emerg | alert | crit | error | warn | notice | info | debug" in msg, msg
    assert "LogLevel requires level" in msg, msg

def _start_process(server_root, **kwargs):
    d = dict(Listen="1234", LogLevel="debug")
    d.update(kwargs)
    config_filename = write_config(server_root, d)
    process = run._create_process([argv0, "-f", config_filename])
    process.read_config()
    return process
    

def test_save_pid():
    # Normal configuration
    with config_tempdir() as server_root:
        process = _start_process(server_root)
        pid_filename = os.path.join(server_root, "logs", "akara.pid")
        assert not os.path.exists(pid_filename)
        process.save_pid()
        assert os.path.exists(pid_filename)
        msg = _get_log(server_root)
        assert "PID file" not in msg.lower(), msg

def test_save_pid_existing_file():
    with config_tempdir() as server_root:
        process = _start_process(server_root)
        pid_filename = os.path.join(server_root, "logs", "akara.pid")
        assert not os.path.exists(pid_filename)
        open(pid_filename, "w").write("already exists!")
        process.save_pid()
        assert os.path.exists(pid_filename)
        msg = _get_log(server_root)
        assert "PID file" in msg, msg
        
        s = open(pid_filename).read()
        pid = int(s)
        assert pid == os.getpid(), (pid, os.getpid())

def test_save_pid_not_writeable():
    with config_tempdir() as server_root:
        process = _start_process(server_root, PidFile="/dev/null/does/not/exist")
        try:
            process.save_pid()
            raise AssertionError("should have died")
        except SystemExit:
            pass
        msg = _get_log(server_root)
        assert "Unable to open PID file" in msg, msg


# XXX testing the inability to "fd.write(str(pid))" and to
# "fd.close()" requires enough work that I'll defer doing that now.

def test_remove_pid():
    with config_tempdir() as server_root:
        process = _start_process(server_root)
        process.save_pid()
        pid_filename = os.path.join(server_root, "logs", "akara.pid")
        assert os.path.exists(pid_filename)
        process.remove_pid()
        assert not os.path.exists(pid_filename)
        msg = _get_log(server_root)
        assert "Removed PID file" in msg, msg
        process.remove_pid()
        msg = _get_log(server_root)
        assert "Unable to remove PID file" not in msg, msg

        process.pid_file = os.path.join(server_root, "logs")
        process.remove_pid()
        msg = _get_log(server_root)
        assert "Unable to remove PID file" in msg, msg


def test_reclaim_servers():
    action_log = []
    class FakeServer(object):
        def __init__(self, name, count):
            self.name = name  # used in logging
            self.count = count
            self.active = True
        def __nonzero__(self):
            return bool(self.count)
        def _check(self, event):
            action_log.append( "%s %s %s" % (event, self.name, self.count))
            if self.count:
                self.count -= 1
                self.active = (self.count > 0)
        def stop(self):
            self._check("stop")
        def terminate(self):
            self._check("terminate")
        def kill(self):
            self._check("kill")

    with config_tempdir() as server_root:
        process = _start_process(server_root)
        process.listeners = []
        process.servers = [FakeServer("spam", 1), FakeServer("eggs", 4),
                           FakeServer("bacon", 7), FakeServer("ni", 200)]
        # Use my own _sleep so I don't need to wait
        process.reclaim_servers(_sleep = lambda t: 1)
        msg = _get_log(server_root)

    assert action_log == ['stop spam 1', 'stop eggs 4', 'stop bacon 7', 'stop ni 200',
                                         'stop eggs 3', 'stop bacon 6', 'stop ni 199',
                                         'stop eggs 2', 'stop bacon 5', 'stop ni 198',
                                         'stop eggs 1', 'stop bacon 4', 'stop ni 197',
                                                        'stop bacon 3', 'stop ni 196',
                                                   'terminate bacon 2', 'terminate ni 195',
                                                   'terminate bacon 1', 'terminate ni 194',
                                                                        'kill ni 193'], action_log

        
    assert "Server 'spam' still did not exit" not in msg, msg
    assert "Server 'eggs' still did not exit" not in msg, msg
    assert "Server 'bacon' still did not exit, terminating" in msg, msg
    assert "Server 'ni' still did not exit, terminating" in msg, msg
    assert "Server 'bacon' still did not exit, killing" not in msg, msg
    assert "Server 'ni' still did not exit, killing" in msg, msg
    assert "Could not make server 'ni' exit" in msg, msg


class RunningServer(object):
    started = False
    stopped = False
    def __init__(self, active, ready):
        self.active = active
        self.ready = ready
    def start(self):
        self.started = True
    def stop(self):
        self.stopped = True

def IdleServer(): return RunningServer(active=1, ready=1)
def InactiveServer(): return RunningServer(active=0, ready=0)
def start_new_server(slot, server):
    return RunningServer(active=1, ready=0)


def test_idle_cull():
    fake_servers = [IdleServer(), IdleServer(),
                    None, InactiveServer(),
                    IdleServer(), IdleServer(),
                    InactiveServer(), None] + [IdleServer() for i in range(10)]

    with config_tempdir() as server_root:
        process = _start_process(server_root)
        assert process.min_spare_servers == 5, process.min_spare_servers
        assert process.max_spare_servers == 10, process.max_spare_servers

        process.servers = fake_servers
        process.idle_maintenance()

        # All of the inactive ones should be gone
        for i, slot in enumerate(process.servers):
            if i in (2, 3, 6, 7):
                assert slot is None, (i, slot)
            else:
                assert slot is not None, (i, slot)
        # The last one (an IdleServer) should be stopped
        assert process.servers[-1].stopped
        
        msg = _get_log(server_root)
        assert "Purging 2 unused servers" in msg, msg
        

def test_idle_spawn():
    fake_servers = [None] * 50

    with config_tempdir() as server_root:
        process = _start_process(server_root,
                                 MinSpareServers=3, MaxSpareServers=8, MaxServers=50)
        assert process.min_spare_servers == 3
        assert process.max_spare_servers == 8
        assert process.max_servers == 50

        process.servers = fake_servers
        process.server_type = start_new_server
        process._idle_spawn_rate = 1

        process.idle_maintenance()
        # Should have added 1 server
        assert fake_servers[0] is not None
        assert fake_servers[1:] == [None] * (len(fake_servers)-1)
        assert process._idle_spawn_rate == 2

        process.idle_maintenance()
        # Should have added 2 servers
        assert None not in fake_servers[:3]
        assert fake_servers[3:] == [None] * (len(fake_servers)-3)
        assert process._idle_spawn_rate == 4
        msg = _get_log(server_root)
        assert "Creating 2 new servers" in msg
        assert "Server seems busy" not in msg

        process.idle_maintenance()
        # Should have added 4 servers
        assert None not in fake_servers[:7]
        assert fake_servers[7:] == [None] * (len(fake_servers)-7)
        assert process._idle_spawn_rate == 8
        msg = _get_log(server_root)
        assert "Server seems busy" not in msg

        process._idle_spawn_rate = 21
        process.idle_maintenance()
        # Should have added 21 servers
        assert None not in fake_servers[:28]
        assert fake_servers[28:] == [None] * (len(fake_servers)-28)
        assert process._idle_spawn_rate == 32, process._idle_spawn_rate  # MAX_SPAWN_RATE
        msg = _get_log(server_root)
        assert "Reached MaxServers" not in msg
        assert "Creating 22 new servers" not in msg
        assert "Server seems busy" in msg
        
        process.idle_maintenance()
        # Should have added 22 servers
        msg = _get_log(server_root)
        assert "Creating 22 new servers" in msg, msg

        process.idle_maintenance()
        # All slots full
        assert None not in fake_servers
        msg = _get_log(server_root)
        assert "Reached MaxServers" in msg, msg
        assert process._idle_spawn_rate == 1

def test_idle_do_nothing():
    fake_servers = [IdleServer() for i in range(10)]

    with config_tempdir() as server_root:
        process = _start_process(server_root,
                                 MinSpareServers=3, MaxSpareServers=10, MaxServers=10)
        process.servers = fake_servers
        process.server_type = None
        process._idle_spawn_rate = 4
        process.idle_maintenance()
        assert process._idle_spawn_rate == 1
