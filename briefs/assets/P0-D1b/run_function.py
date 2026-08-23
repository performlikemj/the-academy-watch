def run(dry_run=False) -> dict:
    """Run every maintenance step once. Returns counts so a caller (or a test) can see what happened."""
    if dry_run:
        retention = video_retention.expire_raw_footage(dry_run=True)
        logger.info("video maintenance dry run: nothing changed (%d match(es) due for expiry)", retention["due"])
        return {"stale_failed": 0, "retention": retention, "dry_run": True}
    stale = video_queue.reap_stale_jobs()
    retention = video_retention.expire_raw_footage()
    logger.info(
        "video maintenance: stale-failed %d job(s); footage expired %d of %d due (%d failed)",
        stale,
        retention["expired"],
        retention["due"],
        retention["failed"],
    )
    return {"stale_failed": stale, "retention": retention, "dry_run": False}
