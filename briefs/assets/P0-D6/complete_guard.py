    from src.services.video_queue import JobFenced  # local import avoids cycles

    if job.status != "running":
        raise JobFenced(f"job {job_id} is no longer running (status={job.status}); results discarded")
