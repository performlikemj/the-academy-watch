"""Keep container diagnostics; access logs omit queries and headers."""

from gunicorn.glogging import Logger
from src.utils.log_privacy import protect_log_handlers


def access_path(value):
    path = str(value).split("?", 1)[0]
    return "/".join("[masked]" if "%" in part or "@" in part else part for part in path.split("/"))


def _request_args(msg, args):
    # gunicorn 26.x: Worker.handle_error -> exception(template, method, uri).
    if isinstance(msg, str) and msg.startswith("Error handling request") and args:
        return (*args[:-1], access_path(args[-1]))
    return args


class PrivacyGunicornLogger(Logger):
    def setup(self, cfg):
        super().setup(cfg)
        protect_log_handlers()

    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        # Worker.handle_error uses default_environ, which omits PATH_INFO.
        if not environ.get("PATH_INFO"):
            atoms["U"] = getattr(req, "path", None) or getattr(req, "uri", "/")
        return {
            key: access_path(atoms[key]) if key == "U" else atoms[key]
            for key in ("t", "h", "m", "U", "H", "s", "b", "L")
        }

    def error(self, msg, *args, **kwargs):
        return super().error(msg, *_request_args(msg, args), **kwargs)

    def exception(self, msg, *args, **kwargs):
        # Preserve the original exception and complete traceback, redacted by
        # the handler backstop, exactly like Gunicorn's native exception().
        return super().exception(msg, *_request_args(msg, args), **kwargs)
