#!/usr/bin/python3
"""Keep untrusted OpenLogi output out of Quickshell until it is bounded."""

import os
import selectors
import signal
import stat
import subprocess
import sys
import time


STDOUT_LIMIT = 64 * 1024
STDERR_LIMIT = 8 * 1024
TIMEOUT_SECONDS = 5
ERRORS = {
    120: b"openlogi list exceeded the stdout limit\n",
    121: b"openlogi list exceeded the stderr limit\n",
    122: b"openlogi list timed out\n",
    123: b"OpenLogi helper failed or was cancelled\n",
    126: b"OpenLogi executable is not trusted\n",
    127: b"openlogi command not found\n",
}


class GuardFailure(Exception):
    def __init__(self, code):
        self.code = code


def trusted_executable():
    """Accept only the system installation, including its parent directories."""
    executable = "/usr/bin/openlogi"
    try:
        for path in ("/", "/usr", "/usr/bin", executable):
            info = os.lstat(path)
            valid_type = stat.S_ISREG if path == executable else stat.S_ISDIR
            if (not valid_type(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022):
                raise GuardFailure(126)
        if not os.access(executable, os.X_OK):
            raise GuardFailure(126)
    except FileNotFoundError:
        raise GuardFailure(127) from None
    except OSError:
        raise GuardFailure(126) from None
    return executable


def collect(command, owner_pid=None):
    """Return bounded binary streams; failures never return partial output."""
    cancelled = False

    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True

    signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    previous = {sig: signal.signal(sig, cancel) for sig in signals}
    process = None
    deadline = time.monotonic() + TIMEOUT_SECONDS
    stdout = bytearray()
    stderr = bytearray()
    try:
        if owner_pid is not None and os.getppid() != owner_pid:
            raise GuardFailure(123)
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
            env={"PATH": "/usr/bin", "LC_ALL": "C",
                 # OpenLogi locates its background agent's socket here.
                 "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"},
            cwd="/",
        )
        with selectors.DefaultSelector() as selector:
            for stream, buffer, limit, code in (
                (process.stdout, stdout, STDOUT_LIMIT, 120),
                (process.stderr, stderr, STDERR_LIMIT, 121),
            ):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, (buffer, limit, code))

            while True:
                if cancelled or (owner_pid is not None and os.getppid() != owner_pid):
                    raise GuardFailure(123)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise GuardFailure(122)

                # Short waits also observe cancellation without signal exceptions
                # interrupting process creation or cleanup.
                interval = min(remaining, 0.1)
                if not selector.get_map():
                    try:
                        code = process.wait(timeout=interval)
                        return code if code in (0, 2) else 1, stdout, stderr
                    except subprocess.TimeoutExpired:
                        continue

                for key, _events in selector.select(interval):
                    buffer, limit, code = key.data
                    try:
                        chunk = os.read(key.fd, min(4096, limit - len(buffer) + 1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(buffer) + len(chunk) > limit:
                        raise GuardFailure(code)
                    else:
                        buffer.extend(chunk)
    except FileNotFoundError:
        raise GuardFailure(127) from None
    finally:
        try:
            if process is not None:
                # Do not poll/reap early: the leader may have exited while a
                # descendant still holds a pipe. Its group must still be killed.
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.stdout.close()
                process.stderr.close()
                process.wait()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main(owner_pid=None):
    try:
        code, stdout, stderr = collect([trusted_executable(), "list"], owner_pid)
    except GuardFailure as failure:
        code, stdout, stderr = failure.code, b"", ERRORS[failure.code]
    except Exception:
        # Never forward exception messages or tracebacks containing producer data.
        code, stdout, stderr = 123, b"", ERRORS[123]

    try:
        sys.stdout.buffer.write(stdout)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(stderr)
        sys.stderr.buffer.flush()
    except BrokenPipeError:
        # The consumer disappeared; the producer has already been reaped.
        os._exit(123)
    return code


def run():
    # Quickshell SIGKILLs its immediate child when the service is destroyed.
    # Keep the guard in a worker that can still kill/reap the producer after
    # that launcher dies. Only the guard writes to the inherited QML pipes.
    owner_pid = os.getpid()
    try:
        worker_pid = os.fork()
    except OSError:
        os.write(2, ERRORS[123])
        return 123
    if worker_pid == 0:
        os._exit(main(owner_pid))

    def cancel(_signum, _frame):
        # The worker observes our exit, including SIGKILL, through getppid().
        raise SystemExit(123)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, cancel)
    _, status = os.waitpid(worker_pid, 0)
    code = os.waitstatus_to_exitcode(status)
    return code if code >= 0 else 123


if __name__ == "__main__":
    sys.exit(run())
