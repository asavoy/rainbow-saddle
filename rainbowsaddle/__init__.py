from __future__ import print_function

import os
import os.path as op
import sys
import atexit
import subprocess
import signal
import time
import argparse
import tempfile
import functools
import traceback

import psutil

from rainbowsaddle.debug_log import debug


def signal_handler(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            debug('Uncaught exception in signal handler %s', func)
            print('Uncaught exception in signal handler %s' % func,
                    file=sys.stderr)
            traceback.print_exc()
    return wrapper


class RainbowSaddle(object):

    def __init__(self, options):
        debug('__init__()')
        self.stopped = False
        # Create a temporary file for the gunicorn pid file
        debug('\t__init__() - Create temporary file for the gunicorn pid file')
        fp = tempfile.NamedTemporaryFile(prefix='rainbow-saddle-gunicorn-',
                suffix='.pid', delete=False)
        fp.close()
        self.pidfile = fp.name
        # Start gunicorn process
        debug('\t__init__() - Start gunicorn process')
        args = options.gunicorn_args + ['--pid', self.pidfile]
        process = subprocess.Popen(args)
        self.arbiter_pid = process.pid
        debug('\t__init__() - Started gunicorn process, self.arbiter_pid == %s', self.arbiter_pid)
        # Install signal handlers
        debug('\t__init__() - Install signal handlers')
        signal.signal(signal.SIGHUP, self.restart_arbiter)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, self.stop)
        debug('\t__init__() - ended')

    def run_forever(self):
        debug('run_forever()')
        while not self.stopped:
            time.sleep(1)
        debug('\trun_forever() - ended')

    @signal_handler
    def restart_arbiter(self, signum, frame):
        debug('restart_arbiter(%s, %s)', signum, frame)
        # Fork a new arbiter
        debug('\trestart_arbiter(...) - Fork a new arbiter')
        debug('\trestart_arbiter(...) - self.arbiter_pid == %s', self.arbiter_pid)
        try:
            process = psutil.Process(self.arbiter_pid)
            debug('\t\tProcess(self.arbiter_id).is_running() == %s', process.is_running())
            debug('\t\tProcess(self.arbiter_id).cmdline == %s', process.cmdline)
        except psutil.NoSuchProcess as e:
            debug('\t\tProcess(self.arbiter_id) => NoSuchProcess (%s)', e)

        self.log('Starting new arbiter')
        os.kill(self.arbiter_pid, signal.SIGUSR2)

        # Wait until pidfile has been renamed
        debug('\trestart_arbiter(...) - Wait until pidfile has been renamed')
        old_pidfile = self.pidfile + '.oldbin'
        while True:
            if op.exists(old_pidfile):
                break
            time.sleep(0.3)

        # Gracefully kill old workers
        debug('\trestart_arbiter(...) - Gracefully kill old workers')
        debug('\trestart_arbiter(...) - Stoping old arbiter with PID %s', self.arbiter_pid)
        self.log('Stoping old arbiter with PID %s' % self.arbiter_pid)
        os.kill(self.arbiter_pid, signal.SIGTERM)
        self.wait_pid(self.arbiter_pid)

        # Read new arbiter PID, being super paranoid about it (we read the PID
        # file until we get the same value twice)
        debug('\trestart_arbiter(...) - Read new arbiter PID')
        prev_pid = None
        while True:
            if op.exists(self.pidfile):
                with open(self.pidfile) as fp:
                    try:
                        pid = int(fp.read())
                    except ValueError:
                        pass
                    else:
                        if prev_pid == pid:
                            break
                        prev_pid = pid
            else:
                print('pidfile not found: ' + self.pidfile)
            time.sleep(0.3)
        self.arbiter_pid = pid
        debug('\trestart_arbiter(...) - New arbiter PID is %s', self.arbiter_pid)
        self.log('New arbiter PID is %s' % self.arbiter_pid)
        debug('\trestart_arbiter(...) - ended')

    def stop(self, signum, frame):
        debug('stop(%s, %s)', signum, frame)
        os.kill(self.arbiter_pid, signal.SIGTERM)
        debug('\tstop(...) - wait_pid()')
        self.wait_pid(self.arbiter_pid)
        self.stopped = True
        debug('\tstop(...) - ended')

    def log(self, msg):
        print('-' * 78, file=sys.stderr)
        print(msg, file=sys.stderr)
        print('-' * 78, file=sys.stderr)
        debug('-' * 78)
        debug(msg)
        debug('-' * 78)

    def wait_pid(self, pid):
        """
        Wait until process *pid* exits.
        """
        debug('wait_pid(%s)', pid)
        try:
            os.waitpid(pid, 0)
        except OSError, err:
            debug("\twait_pid(%s) - err == %s", err)
            debug("\twait_pid(%s) - err.errno == %s", err.errno)
            if err.errno == 10:
                debug("\twait_pid(%s) - if err.errno == 10")
                while True:
                    try:
                        process = psutil.Process(pid)
                        if process.status == 'zombie':
                            debug("\twait_pid(%s) - process.status == 'zombie'", pid)
                            break
                    except psutil.NoSuchProcess:
                        debug('\twait_pid(%s) - NoSuchProcess', pid)
                        break
                    time.sleep(0.1)


def main():
    # Parse command line
    parser = argparse.ArgumentParser(description='Wrap gunicorn to handle '
            'graceful restarts correctly')
    parser.add_argument('--pid',  help='a filename to store the '
            'rainbow-saddle PID')
    parser.add_argument('gunicorn_args', nargs=argparse.REMAINDER, 
            help='gunicorn command line')
    options = parser.parse_args()

    # Write pid file
    if options.pid is not None:
        with open(options.pid, 'w') as fp:
            fp.write('%s\n' % os.getpid())
        atexit.register(os.unlink, options.pid)

    # Run script
    saddle = RainbowSaddle(options)
    saddle.run_forever()
