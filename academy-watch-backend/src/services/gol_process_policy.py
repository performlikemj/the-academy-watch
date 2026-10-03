"""Mandatory OS policy for the analysis worker, installed before input is read."""

import ctypes
import os
import resource
import signal
import sys

CPU_SECONDS = 10
ADDRESS_SPACE_BYTES = 768 * 1024 * 1024
# Linux child RSS ceiling; admission can assign a lower cap from cgroup headroom.
RSS_BYTES = 448 * 1024 * 1024


def set_limits(cpu_seconds=CPU_SECONDS, address_space_bytes=ADDRESS_SPACE_BYTES, expected_parent_pid=None):
    if sys.platform != "linux":
        raise RuntimeError("Analysis isolation unavailable")
    if sys.platform == "linux":
        parent_pid = os.getppid() if expected_parent_pid is None else expected_parent_pid
        libc = ctypes.CDLL(None, use_errno=True)
        _checked(libc.prctl(1, signal.SIGKILL, 0, 0, 0))  # PR_SET_PDEATHSIG
        if parent_pid <= 0 or os.getppid() != parent_pid:
            raise RuntimeError("Analysis isolation unavailable")
    # A secondary wall timer bounds lifecycle if supervision is interrupted.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(20)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    os.nice(10)
    # Prefer the disposable child if a container-wide OOM still occurs.
    with open("/proc/self/oom_score_adj", "w") as score:
        score.write("500")


def _checked(value):
    if value < 0:
        raise OSError(ctypes.get_errno(), "Analysis isolation unavailable")
    return value


def _linux_filesystem():
    """Landlock ABI 3 handles all filesystem rights including truncate."""
    libc = ctypes.CDLL(None, use_errno=True)
    # Landlock syscall numbers are shared by supported x86_64/aarch64 Linux.
    if os.uname().machine not in {"x86_64", "aarch64"}:
        raise RuntimeError("Analysis isolation unavailable")
    abi = _checked(libc.syscall(444, 0, 0, 1))
    if abi < 3:
        raise RuntimeError("Analysis isolation unavailable")
    _checked(libc.prctl(38, 1, 0, 0, 0))  # PR_SET_NO_NEW_PRIVS

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    ruleset = Ruleset((1 << 15) - 1)
    ruleset_fd = _checked(libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0))
    directory_fd = os.open(".", os.O_PATH | os.O_CLOEXEC)
    try:
        rule = PathRule((1 << 2) | (1 << 3), directory_fd)  # READ_FILE | READ_DIR, cwd only
        _checked(libc.syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0))
        _checked(libc.syscall(446, ruleset_fd, 0))
    finally:
        os.close(directory_fd)
        os.close(ruleset_fd)


def _linux_syscalls():
    """Default-deny native syscalls; no sockets, process creation or process access."""
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x00050000 | 1)  # SCMP_ACT_ERRNO(EPERM)
    if not context:
        raise RuntimeError("Analysis isolation unavailable")
    try:
        # The worker must be single-threaded before Landlock; TSYNC is required
        # too, so any future bootstrap change cannot leave an unfiltered thread.
        _checked(lib.seccomp_attr_set(context, 4, 1))  # SCMP_FLTATR_CTL_TSYNC
        allowed = [
            "read",
            "write",
            "readv",
            "writev",
            "close",
            "fstat",
            "newfstatat",
            "stat",
            "lstat",
            "statx",
            "lseek",
            "pread64",
            "getdents64",
            "open",
            "openat",
            "readlink",
            "readlinkat",
            "access",
            "faccessat",
            "faccessat2",
            "mmap",
            "mmap2",
            "munmap",
            "mremap",
            "mprotect",
            "brk",
            "madvise",
            "rt_sigreturn",
            "sigaltstack",
            "futex",
            "futex_time64",
            "set_robust_list",
            "rseq",
            "clock_gettime",
            "clock_gettime64",
            "clock_getres",
            "gettimeofday",
            "time",
            "nanosleep",
            "clock_nanosleep",
            "clock_nanosleep_time64",
            "getpid",
            "getppid",
            "gettid",
            "getuid",
            "geteuid",
            "getgid",
            "getegid",
            "sched_yield",
            "sched_getaffinity",
            "getcpu",
            "uname",
            "sysinfo",
            "getrusage",
            "getrandom",
            "fcntl",
            "ioctl",
            "restart_syscall",
            "exit",
            "exit_group",
        ]
        for name in allowed:
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number >= 0:
                _checked(lib.seccomp_rule_add(context, 0x7FFF0000, number, 0))
        _checked(lib.seccomp_load(context))
    finally:
        lib.seccomp_release(context)


def install_policy():
    if sys.platform == "linux":
        # Landlock applies to the calling thread; no pre-existing worker may
        # bypass it. BLAS threads are disabled during the trusted bootstrap.
        if len(os.listdir("/proc/self/task")) != 1:
            raise RuntimeError("Analysis isolation unavailable")
        # Load seccomp before installing the filesystem restriction.
        ctypes.CDLL("libseccomp.so.2", use_errno=True)
        _linux_filesystem()
        _linux_syscalls()
    else:
        raise RuntimeError("Analysis isolation unavailable")
