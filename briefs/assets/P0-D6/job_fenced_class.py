

class JobFenced(RuntimeError):
    """The job is no longer ours: it was reaped (or cancelled) while a worker still held it. Workers stop and
    write nothing; completion refuses. Keeps a zombie worker from clobbering a requeued job or its match."""


