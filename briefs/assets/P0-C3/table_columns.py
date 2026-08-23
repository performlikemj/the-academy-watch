def _introspect_table_columns(table_name: str) -> set[str]:
    # Stay on the session's transaction. An inspector-owned wrapper can roll
    # back SQLite's shared in-memory connection when it closes mid-request.
    bind = db.session.connection()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_columns(table_name: str) -> set[str]:
    """Introspect once per HTTP request; the schema cannot change mid-request and the
    registry is consulted up to a dozen times per contact-rail call. No cache outside a request."""
    if not has_request_context():
        return _introspect_table_columns(table_name)
    cache = getattr(request, "_club_registry_columns", None)
    if cache is None:
        cache = {}
        request._club_registry_columns = cache
    if table_name not in cache:
        cache[table_name] = _introspect_table_columns(table_name)
    return cache[table_name]
