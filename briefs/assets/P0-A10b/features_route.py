

@auth_bp.route("/features", methods=["GET"])
def features():
    """Public feature flags the client gates its entry points on (no auth; booleans only)."""
    from src.services.contact import contact_rail_enabled

    return jsonify({"contact_rail": contact_rail_enabled()})
