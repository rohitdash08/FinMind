import unittest
from app import create_app
from app.extensions import scheduler

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.scheduler = scheduler

    def test_job_registration(self):
        job = self.scheduler.get_job('reminder_job')
        self.assertIsNotNone(job)
        self.assertEqual(job.name, 'reminder_job')

if __name__ == '__main__':
    unittest.main()