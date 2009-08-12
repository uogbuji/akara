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
from akara.server import logger

argv0 = sys.argv[0]

def test_process_default():
    process = server.create_process([argv0])
    assert process.ident == 'akara'
    assert process.config_file.startswith(os.path.expanduser("~"))
    # Check that it's at the default level
    assert process.log_level == logger.LOG_WARN

def test_process_debug():
    process = server.create_process([argv0, "-X"])
    assert process.log_level == logger.LOG_DEBUG


# The config reader has side-effects. It does a FQDN lookup and writes to a log file.
@contextlib.contextmanager
def config_tempdir():
    old_sys_stderr = sys.stderr
    server_root = tempfile.mkdtemp(prefix="test_akara_server_config")
    os.mkdir(os.path.join(server_root, "logs"))
    try:
        yield server_root
    finally:
        # Restore any changes to sys.stderr
        # (Might be done as part of process.read_config() )
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
            process = server.create_process([argv0, "-f", "/does/not/exist", "-X"])
            try:
                process.read_config()
            except SystemExit:
                # ignore the SystemExit because no port was specified
                pass
        msg = stderr.getvalue()
        assert "does/not/exist" in msg, msg
        assert "no listening sockets available" in msg, msg


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
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 80)

        # Also check a few of the other variables
        assert process.server_root == server_root, process.server_root
        assert process.pid_file.startswith(server_root), process.pid_file
        assert process.error_log.startswith(server_root), process.error_log
        


    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen=":810"))
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 810)

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="localhost:8765"))
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("localhost", 8765)

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234"))
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.server_addr == ("", 1234)



def test_process_no_error_log():
    stderr = StringIO()
    with capturing_stderr(stderr):
        with config_tempdir() as server_root:
            config_filename = write_config(server_root, dict(Listen="1234", ErrorLog="/does/not/exist"))
            process = server.create_process([argv0, "-f", config_filename])
            try:
                process.read_config()
                raise AssertionError("but there was no error log!")
            except SystemExit:
                pass
    msg = stderr.getvalue()
    assert "could not open error log file"  in msg, msg
    assert "/does/not/exist" in msg, msg


def test_process_log_levels():
    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="debug",
                                                         ErrorLog = "spam.log"))
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        process.log.debug("Spam!")
        content = open(os.path.join(server_root, "spam.log")).read()
        assert "Spam!" in content, content


    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="info",
                                                         ErrorLog = "spam.log"))
        process = server.create_process([argv0, "-f", config_filename])
        process.read_config()
        assert process.debug == False
        process.log.debug("Spam!")
        content = open(os.path.join(server_root, "spam.log")).read()
        assert "Spam!" not in content, content

    with config_tempdir() as server_root:
        config_filename = write_config(server_root, dict(Listen="1234", LogLevel="info",
                                                         ErrorLog = "spam.log"))
        process = server.create_process([argv0, "-f", config_filename, "-X"])  # Added -X
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
            process = server.create_process([argv0, "-f", config_filename])
            try:
                process.read_config()
                raise AssertionError("Did not catch the bad log level")
            except SystemExit:
                pass
    msg = stderr.getvalue()
    assert "emerg | alert | crit | error | warn | notice | info | debug" in msg, msg
    assert "LogLevel requires level" in msg, msg

        



