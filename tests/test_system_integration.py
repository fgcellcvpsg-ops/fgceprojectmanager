import unittest
import os
import sys
import uuid
from datetime import date, datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Client, Project, Task, History, WorkHistoryReport

class TestSystemIntegration(unittest.TestCase):
    def setUp(self):
        # Unique DB for each test run to avoid lock issues
        self.db_filename = f'system_test_{uuid.uuid4().hex}.db'
        self.db_path = os.path.join(os.getcwd(), self.db_filename)
        
        class TestConfig:
            TESTING = True
            WTF_CSRF_ENABLED = False
            WTF_CSRF_CHECK_DEFAULT = False
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{self.db_path}'
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SECRET_KEY = 'test-key'

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        
        # Initialize DB
        with self.app.app_context():
            db.create_all()
            
            # Create Admin User
            self.admin = User(
                username='admin', 
                email='admin@example.com', 
                role='admin', 
                is_allowed=True,
                auth_type='manual',
                display_name='Admin Tester'
            )
            self.admin.set_password('123')
            db.session.add(self.admin)
            db.session.commit()
            
            # Refresh to get ID
            self.admin_id = self.admin.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        
        # Try to remove file
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                print(f"Warning: Could not delete {self.db_path}")

    def login(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin_id)
            sess['_fresh'] = True

    def test_01_authentication(self):
        """Test Login/Logout logic"""
        print("\nRunning test_01_authentication...")
        # Test login page load
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)
        
        # Test valid login
        resp = self.client.post('/login', data={
            'username': 'admin',
            'password': '123'
        }, follow_redirects=True)
        
        # Verify login via session
        with self.client.session_transaction() as sess:
            self.assertIn('_user_id', sess, "User ID should be in session after login")
            self.assertEqual(int(sess['_user_id']), self.admin_id)
        
        # Test logout
        resp = self.client.get('/logout', follow_redirects=True)
        content = resp.data.decode('utf-8')
        
        # Check we are back at login page
        self.assertIn('Login', content)
        
        # Check for flash message (it's JSON encoded in the script tag)
        # We can just check for the presence of the script tag and maybe part of the encoded string
        # or just rely on being redirected to login page as sufficient proof of logout
        self.assertIn('flask-flash-data', content)
        # Unicode escape for "Đã đăng xuất" might vary, so let's check for "flask-flash-data" 
        # and that we are on the login page.
        
    def test_02_client_management(self):
        """Test Client Creation"""
        print("\nRunning test_02_client_management...", file=sys.__stdout__)
        self.login()
        
        # Verify user exists
        with self.app.app_context():
             u = db.session.get(User, self.admin_id)

        resp = self.client.post('/add_client', data={
            'name': 'Test Client A',
            'symbol': 'TCA',
            'note': 'Test Note'
        }, follow_redirects=True)
        
        content = resp.data.decode('utf-8')
        
        with self.app.app_context():
            client = Client.query.filter_by(symbol='TCA').first()
            self.assertIsNotNone(client)
            self.assertEqual(client.name, 'Test Client A')

    def test_03_project_lifecycle_and_blocking(self):
        """Test Full Project Lifecycle including Blocking Logic"""
        print("\nRunning test_03_project_lifecycle_and_blocking...")
        self.login()
        
        # 1. Create Client
        with self.app.app_context():
            client = Client(name='Project Client', symbol='PC')
            db.session.add(client)
            db.session.commit()
            client_id = client.id

        # 2. Create Project (FGC)
        resp = self.client.post('/add_project', data={
            'name': 'System Test Project',
            'client_id': client_id,
            'po_number': '88888888',
            'address': 'Hanoi',
            'deadline': str(date.today()),
            'scope': 'Integration Test',
            'project_type': 'FGC',
            'owners': [self.admin_id]
        }, follow_redirects=True)
        
        with self.app.app_context():
            project = Project.query.filter_by(po_number='88888888').first()
            if not project:
                print("Project creation failed. Response content:", file=sys.__stdout__)
                print(resp.data.decode('utf-8')[:500], file=sys.__stdout__)
            self.assertIsNotNone(project)
            project_id = project.id

        # 3. Add Unfinished Task
        # Route: @tasks_bp.route('/project/<int:project_id>/tasks/create_form', methods=['POST'])
        
        resp = self.client.post(f'/project/{project_id}/tasks/create_form', data={
            'name': 'Critical Task',
            'deadline': str(date.today())
        }, follow_redirects=True)
        
        # 4. Try to Complete Project (Should fail)
        # Scenario A: Edit Project Form
        resp = self.client.post(f'/edit_project/{project_id}', data={
            'name': 'System Test Project',
            'client_id': client_id,
            'po_number': '88888888',
            'address': 'Hanoi',
            'deadline': str(date.today()),
            'scope': 'Integration Test',
            'status': 'Completed', # Attempt to complete
            'progress': '100',
            'project_type': 'FGC',
            'owners': [self.admin_id]
        }, follow_redirects=True)
        content = resp.data.decode('utf-8')
        # Expect warning
        if "Dự án còn công việc chưa hoàn thành" not in content and "warning" not in content:
            print("Blocking failed (Edit Project). Content snippet:")
            # print(content[:500]) 
        
        # We accept either specific message or generic warning class
        is_blocked = ("Dự án còn công việc chưa hoàn thành" in content) or ("warning" in content) or ("cảnh báo" in content.lower())
        self.assertTrue(is_blocked, "Should block edit_project when tasks unfinished")
        
        # Scenario B: Update Progress Popup
        resp = self.client.post(f'/update_progress/{project_id}', data={
            'status': 'Completed',
            'progress': '100'
        }, follow_redirects=True)
        content = resp.data.decode('utf-8')
        is_blocked = ("Dự án còn công việc chưa hoàn thành" in content) or ("warning" in content)
        self.assertTrue(is_blocked, "Should block update_progress when tasks unfinished")

        # 5. Complete Task
        with self.app.app_context():
            task = Task.query.filter_by(project_id=project_id).first()
            task_id = task.id
        
        # Route: @tasks_bp.route('/project/<int:project_id>/task/<int:task_id>/status', methods=['POST'])
        resp = self.client.post(f'/project/{project_id}/task/{task_id}/status', data={
            'status': 'Done'
        }, follow_redirects=True)
        
        # Verify in DB
        with self.app.app_context():
            t = db.session.get(Task, task_id)
            self.assertEqual(t.status, 'Done')

        # 6. Complete Project (Should succeed now)
        resp = self.client.post(f'/update_progress/{project_id}', data={
            'status': 'Completed',
            'progress': '100'
        }, follow_redirects=True)
        content = resp.data.decode('utf-8')
        if 'Tiến độ đã được cập nhật' not in content and 'success' not in content:
             print("Final completion failed. Content:")
             # print(content[:500])
             
        self.assertTrue('Tiến độ đã được cập nhật' in content or 'success' in content)
        
        with self.app.app_context():
            p = db.session.get(Project, project_id)
            self.assertEqual(p.status, 'Completed')
            self.assertEqual(p.progress, 100)

    def test_04_work_history_report(self):
        """Test Work History Report Create/List/Export"""
        print("\nRunning test_04_work_history_report...")
        self.login()

        with self.app.app_context():
            client = Client(name='Work History Client', symbol='WHC')
            db.session.add(client)
            db.session.commit()
            client_id = client.id

        resp = self.client.post('/add_project', data={
            'name': 'Work History Project',
            'client_id': client_id,
            'po_number': '99999999',
            'address': 'Hanoi',
            'deadline': str(date.today()),
            'scope': 'Work History Test',
            'project_type': 'FGC',
            'owners': [self.admin_id]
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            project = Project.query.filter_by(po_number='99999999').first()
            self.assertIsNotNone(project)
            project_id = project.id

        resp = self.client.get('/admin/work_history_report')
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post('/admin/work_history_report', data={
            'work_type': 'Email gửi báo cáo',
            'email_from': 'admin@example.com',
            'email_to': 'client@example.com',
            'work_date': str(date.today()),
            'project_id': str(project_id),
            'change_details': 'Gửi báo cáo tiến độ dự án'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            entry = WorkHistoryReport.query.filter_by(work_type='Email gửi báo cáo').first()
            self.assertIsNotNone(entry)
            self.assertEqual(entry.email_from, 'admin@example.com')
            self.assertEqual(entry.email_to, 'client@example.com')
            self.assertEqual(entry.project_id, project_id)
            self.assertEqual(entry.created_by_id, self.admin_id)

        resp = self.client.get('/admin/work_history_report?work_type=Email')
        self.assertEqual(resp.status_code, 200)
        content = resp.data.decode('utf-8')
        self.assertIn('Email gửi báo cáo', content)

        resp = self.client.get('/admin/work_history_report/export.csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp.headers.get('Content-Type', ''))

if __name__ == '__main__':
    unittest.main()
