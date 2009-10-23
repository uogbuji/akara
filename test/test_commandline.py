import tempfile
import shutil
import os

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
# plus do one extra call. It's hard to test that automatically so
# do those tests manually.

def test_get_pid():
    server_root = tempfile.mkdtemp(prefix="akara_test_")    
    try:
        config = Config(os.path.join(server_root))
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
            
    finally:
        shutil.rmtree(server_root)

