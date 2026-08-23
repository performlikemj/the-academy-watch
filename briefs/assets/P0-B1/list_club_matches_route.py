@club_bp.route("/club/<int:program_id>/matches", methods=["GET"])
@require_club_manager()
def list_club_matches(program_id: int):
    """List one program's matches, newest first. Quota caps a program at MAX_MATCH_QUOTA rows, so no paging."""
    rows = (
        VideoMatch.query.filter_by(club_program_id=program_id)
        .order_by(VideoMatch.created_at.desc(), VideoMatch.id.desc())
        .all()
    )
    matches = []
    for match in rows:
        out = match.to_dict(include_job=True)
        out["processing_request_status"] = "requested" if match.processing_requested_at else None
        matches.append(out)
    return jsonify({"matches": matches, "total": len(matches)})


