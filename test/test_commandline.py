from __future__ import with_statement
import tempfile
import shutil
import os
import sys
from cStringIO import StringIO

from akara import commandline, read_config

class Config(object):
    def __init__(self, server_root):
        self.config_filename = os.path.join(server_root, "pid_test.ini")
        self.pid_filename = os.path.join(server_root, "pid.txt")
    def save_pid(self, text):
        f = open(self.pid_filename, "w")
        try:
            f.write(text)
        finally:
            f.close()

# 'akara stop' and 'akara restart' essentially just call get_pid()
# plus do one extra call. The os.kill calls are tested manually.


def tmpdir(func):
    def wrapper():
        dirname = tempfile.mkdtemp(prefix="akara_test_")
        try:
            func(dirname)
        finally:
            shutil.rmtree(dirname)
    wrapper.__name__ = func.__name__
    return wrapper

@tmpdir
def test_get_pid(server_root):
    config = Config(server_root)
    f = open(config.config_filename, "w")
    try:
        f.write("[global]\nPidFile = %s\n" % config.pid_filename)
    finally:
        f.close()
    try:
        commandline.get_pid(config)
        raise AssertionError("But the file does not exist!")
    except SystemExit, err:
        assert "Could not open Akara PID file" in str(err), err
        assert config.pid_filename in str(err), err

    config.save_pid("")
    try:
        commandline.get_pid(config)
    except SystemExit, err:
        assert "Empty Akara PID file" in str(err), err
        assert config.pid_filename in str(err), err

    config.save_pid("hello\n")
    try:
        commandline.get_pid(config)
    except SystemExit, err:
        assert "does not contain a PID" in str(err), err
        assert config.pid_filename in str(err), err

    config.save_pid("123\n")
    pid = commandline.get_pid(config)
    assert pid == 123


class CaptureStdout(object):
    def __init__(self):
        self.io = StringIO()
    def __enter__(self):
        self.io.reset()
        self.io.truncate()
        self.stdout = sys.stdout
        sys.stdout = self.io
    def __exit__(self, *args):
        sys.stdout = self.stdout
        self.content = self.io.getvalue()
        

@tmpdir
def test_status(server_root):
    config = Config(server_root)
    capture = CaptureStdout()
    with capture:
        try:
            commandline.status(config)
            raise AssertionError("should not get here")
        except SystemExit:
            pass
    assert "Could not open Akara configuration file" in capture.content
    assert config.config_filename in capture.content
    assert "Error log file" not in capture.content

    f = open(config.config_filename, "w")
    f.write("[global]\nPidFile = %s\n" % config.pid_filename)
    f.close()
    with capture:
        commandline.status(config)
    assert "PID file" in capture.content
    assert "PID file does not exist" in capture.content
    assert "Akara is not running" in capture.content
    assert "Cannot open PID file" not in capture.content

    config.save_pid("Scobby-doo!\n")
    with capture:
        try:
            commandline.status(config)
            raise AssertionError("where was the exit? %r" % capture.io.getvalue())
        except SystemExit:
            pass
    assert "Unable to parse the PID" in capture.content
    assert "Scobby-doo" in capture.content

    os.chmod(config.pid_filename, 0)
    with capture:
        try:
            commandline.status(config)
            raise AssertionError("where was the exit? %r" % capture.io.getvalue())
        except SystemExit:
            pass
    assert "*** Cannot open PID file" in capture.content


    os.chmod(config.pid_filename, 0644)
    my_pid = str(os.getpid())
    config.save_pid(my_pid)
    with capture:
        commandline.status(config)

    assert ("PID is %s and there is a process" % my_pid) in capture.content
    assert "Akara is running" in capture.content

    # I can't think of a good way to test for a PID which does not exist.
    # That test is done manually.

@tmpdir
def test_setup_config_file(server_root):
    config_file = os.path.join(server_root, "blah_subdir", "test_config.ini")

    assert not os.path.exists(config_file)

    capture = CaptureStdout()
    with capture:
        commandline._setup_config_file(config_file)
    assert "Copying reference configuration file" in capture.content
    assert "Creating directory" in capture.content
    assert "blah_subdir" in capture.content

    assert os.path.exists(config_file)
    s = open(config_file).read()
    assert "[global]" in s
    assert "\nListen" in s

    with capture:
        commandline._setup_config_file(config_file)
    assert "Configuration file already exists" in capture.content

@tmpdir
def test_setup(server_root):
    config = Config(server_root)
    capture = CaptureStdout()

    f = open(config.config_filename, "w")
    f.write("[global]\nServerRoot = %s\n" % server_root)
    f.close()

    with capture:
        commandline.setup(config)

    assert "Created error log directory" in capture.content
    assert "Access log directory exists" in capture.content
    assert "PID file directory exists" in capture.content, capture.content
    assert "Created extension modules directory" in capture.content
    
    assert os.path.exists(os.path.join(server_root, "logs"))
    assert os.path.exists(os.path.join(server_root, "modules"))
