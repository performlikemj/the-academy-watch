"""Container logging boundaries: request metadata only, never headers or queries."""

from gunicorn.glogging import Logger
from src.utils.log_privacy import log_metadata, safe_exc_info


def access_path(value):
    # Percent-encoded segments are untrusted too. Omit the entire segment rather
    # than iteratively decoding arbitrary encodings. Preserve ordinary routing.
    path = value.split("?", 1)[0]
    return "/".join("[masked]" if "%" in part or "@" in part else part for part in path.split("/"))


class PrivacyGunicornLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        # Build a fresh whitelist: neither unused request/response headers nor
        # environ values are passed to the logging subsystem.
        return {
            "t": atoms["t"],
            "h": log_metadata(atoms["h"]),
            "m": log_metadata(atoms["m"]),
            "U": access_path(atoms["U"]),
            "H": atoms["H"]
            if atoms["H"] in {"HTTP/1.0", "HTTP/1.1", "HTTP/2", "HTTP/2.0", "HTTP/3"}
            else "HTTP/unknown",
            "s": log_metadata(atoms["s"]),
            "b": log_metadata(atoms["b"]),
            "L": log_metadata(atoms["L"]),
        }

    def error(self, msg, *args, **kwargs):
        if msg == "Error handling request %s" and args:
            # Gunicorn's inherited error path otherwise logs RAW_URI/query.
            msg, args = "Error handling request path=%s", (access_path(args[0]),)
        else:
            args = tuple(log_metadata(value) for value in args)
        if kwargs.get("exc_info"):
            kwargs["exc_info"] = safe_exc_info()
        return super().error(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        return super().warning(msg, *(log_metadata(value) for value in args), **kwargs)

    def critical(self, msg, *args, **kwargs):
        return super().critical(msg, *(log_metadata(value) for value in args), **kwargs)

    def exception(self, msg, *args, **kwargs):
        kwargs["exc_info"] = safe_exc_info()
        return super().error(msg, *(log_metadata(value) for value in args), **kwargs)

    def debug(self, msg, *args, **kwargs):
        return super().debug(msg, *(log_metadata(value) for value in args), **kwargs)

    def info(self, msg, *args, **kwargs):
        return super().info(msg, *(log_metadata(value) for value in args), **kwargs)
