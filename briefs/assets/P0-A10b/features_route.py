

@api_bp.route("/features", methods=["GET"])
def features():
    """Public feature flags the client gates its entry points on (no auth; booleans only).

    Mirrors src.services.contact.contact_rail_enabled(); kept import-free on purpose — importing the contact
    service here would load the contact models into every test app and break their create_all().
    """
    enabled = os.getenv("CONTACT_RAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return jsonify({"contact_rail": enabled})
