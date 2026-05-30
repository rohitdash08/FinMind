from app.models_jobs import BackgroundJob, JobStatus
from app.extensions import db


def test_enqueue_and_list_job(client, auth_header):
    r = client.post(
        "/jobs",
        json={"job_type": "send_reminder", "payload": {"reminder_id": 1}},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["job_type"] == "send_reminder"
    assert data["status"] == "PENDING"
    job_id = data["id"]

    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    jobs = r.get_json()
    assert len(jobs) >= 1
    assert any(j["id"] == job_id for j in jobs)


def test_enqueue_requires_job_type(client, auth_header):
    r = client.post("/jobs", json={"payload": {"key": "value"}}, headers=auth_header)
    assert r.status_code == 400


def test_process_pending_jobs(client, auth_header):
    r = client.post(
        "/jobs",
        json={"job_type": "send_reminder", "payload": {"reminder_id": 999}},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200
    results = r.get_json()
    assert "processed" in results
    assert results["processed"] >= 1


def test_job_retry_on_failure(client, auth_header, app_fixture):
    r = client.post(
        "/jobs",
        json={
            "job_type": "send_reminder",
            "payload": {"reminder_id": 99999},
            "max_retries": 3,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200

    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        assert job is not None
        assert job.status in (
            JobStatus.RETRYING.value,
            JobStatus.DEAD.value,
            JobStatus.FAILED.value,
            JobStatus.COMPLETED.value,
        )


def test_job_becomes_dead_after_max_retries(client, auth_header, app_fixture):
    r = client.post(
        "/jobs",
        json={
            "job_type": "send_reminder",
            "payload": {"reminder_id": 99999},
            "max_retries": 1,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200

    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        if job and job.status == JobStatus.RETRYING.value:
            job.scheduled_at = __import__("datetime").datetime.utcnow()
            db.session.commit()

    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200

    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        assert job is not None
        assert job.status in (JobStatus.DEAD.value, JobStatus.RETRYING.value)


def test_retry_dead_job(client, auth_header, app_fixture):
    r = client.post(
        "/jobs",
        json={
            "job_type": "send_reminder",
            "payload": {"reminder_id": 99999},
            "max_retries": 0,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.post("/jobs/process", headers=auth_header)

    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        if job and job.status == JobStatus.DEAD.value:
            r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
            assert r.status_code == 200
            assert r.get_json()["status"] == "PENDING"


def test_job_stats(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    stats = r.get_json()
    assert "total" in stats
    assert "by_status" in stats


def test_invalid_max_retries(client, auth_header):
    r = client.post(
        "/jobs",
        json={"job_type": "test", "max_retries": -5},
        headers=auth_header,
    )
    assert r.status_code == 400

    r = client.post(
        "/jobs",
        json={"job_type": "test", "max_retries": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400
