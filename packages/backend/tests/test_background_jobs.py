from datetime import datetime, timedelta


def test_background_job_success_and_listing(client, auth_header):
    r = client.post(
        "/jobs",
        json={"name": "noop", "payload": {"source": "pytest"}},
        headers=auth_header,
    )
    assert r.status_code == 201
    job = r.get_json()
    assert job["status"] == "QUEUED"

    r = client.post("/jobs/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == {"processed": 1, "succeeded": 1, "retrying": 0, "failed": 0}

    r = client.get(f"/jobs/{job['id']}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "SUCCEEDED"

    r = client.get("/jobs?status=SUCCEEDED", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1


def test_background_job_retries_then_fails(client, auth_header, app_fixture):
    r = client.post(
        "/jobs",
        json={"name": "fail", "payload": {"message": "boom"}, "max_attempts": 2},
        headers=auth_header,
    )
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.post("/jobs/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retrying"] == 1

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    job = r.get_json()
    assert job["status"] == "RETRYING"
    assert job["attempts"] == 1
    assert "boom" in job["last_error"]

    # Make the retry due now and prove the bounded retry budget is enforced.
    retry_due = datetime.utcnow() - timedelta(seconds=1)

    from app.extensions import db
    from app.models import BackgroundJob

    with app_fixture.app_context():
        job_row = db.session.get(BackgroundJob, job_id)
        job_row.run_at = retry_due
        db.session.commit()

    r = client.post("/jobs/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["failed"] == 1

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    job = r.get_json()
    assert job["status"] == "FAILED"
    assert job["attempts"] == 2
