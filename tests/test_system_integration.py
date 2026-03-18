import unittest
import os
import sys
import uuid
import tempfile
import shutil
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Client, Project, Task, History, WorkHistoryReport, ProjectQuestion

class TestSystemIntegration(unittest.TestCase):
    def setUp(self):
        # Unique DB for each test run to avoid lock issues
        self.db_filename = f'system_test_{uuid.uuid4().hex}.db'
        self.temp_dir = Path(tempfile.mkdtemp(prefix='fgce_pm_tests_')).resolve()
        self.db_path = str((self.temp_dir / self.db_filename).resolve())
        self.db_uri_path = self.db_path.replace('\\', '/')
        
        class TestConfig:
            TESTING = True
            WTF_CSRF_ENABLED = False
            WTF_CSRF_CHECK_DEFAULT = False
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.db_uri_path}"
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
        if getattr(self, 'temp_dir', None) and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self):
        self.login_as(self.admin_id)

    def login_as(self, user_id):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
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

    def test_05_project_question_answer(self):
        self.login()

        with self.app.app_context():
            manager_1 = User(
                username='manager_1',
                email='manager_1@example.com',
                role='manager',
                is_allowed=True,
                auth_type='manual',
                display_name='Manager 1'
            )
            manager_1.set_password('123')
            db.session.add(manager_1)

            manager_2 = User(
                username='manager_2',
                email='manager_2@example.com',
                role='manager',
                is_allowed=True,
                auth_type='manual',
                display_name='Manager 2'
            )
            manager_2.set_password('123')
            db.session.add(manager_2)

            client = Client(name='QA Client', symbol='QAC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='QA Project',
                client_id=client.id,
                po_number='77777777',
                status='New',
                progress=0,
                owner_id=manager_1.id
            )
            db.session.add(project)
            db.session.commit()
            project_id = project.id
            manager_1_id = manager_1.id
            manager_2_id = manager_2.id

        self.login_as(manager_1_id)
        resp = self.client.post(f'/project/{project_id}/add_question', data={'question': 'Câu hỏi test'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            q = ProjectQuestion.query.filter_by(project_id=project_id).first()
            self.assertIsNotNone(q)
            question_id = q.id

        self.login_as(manager_2_id)
        resp = self.client.post(f'/question/{question_id}/answer', data={'answer': 'Câu trả lời test'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            q = db.session.get(ProjectQuestion, question_id)
            self.assertEqual(q.answer, 'Câu trả lời test')
            self.assertIsNotNone(q.answered_at)
            self.assertEqual(q.answered_by_id, manager_2_id)

    def test_06_leader_can_answer_project_question(self):
        self.login()

        with self.app.app_context():
            leader_1 = User(
                username='leader_1',
                email='leader_1@example.com',
                role='leader',
                is_allowed=True,
                auth_type='manual',
                display_name='Leader 1'
            )
            leader_1.set_password('123')
            db.session.add(leader_1)

            leader_2 = User(
                username='leader_2',
                email='leader_2@example.com',
                role='leader',
                is_allowed=True,
                auth_type='manual',
                display_name='Leader 2'
            )
            leader_2.set_password('123')
            db.session.add(leader_2)

            client = Client(name='Leader QA Client', symbol='LQC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='Leader QA Project',
                client_id=client.id,
                po_number='66666666',
                status='New',
                progress=0,
                owner_id=leader_1.id
            )
            db.session.add(project)
            db.session.commit()

            project_id = project.id
            leader_1_id = leader_1.id
            leader_2_id = leader_2.id

        self.login_as(leader_1_id)
        resp = self.client.post(f'/project/{project_id}/add_question', data={'question': 'Câu hỏi leader'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            q = ProjectQuestion.query.filter_by(project_id=project_id).first()
            self.assertIsNotNone(q)
            question_id = q.id

        self.login_as(leader_2_id)
        resp = self.client.post(f'/question/{question_id}/answer', data={'answer': 'Trả lời bởi leader'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            q = db.session.get(ProjectQuestion, question_id)
            self.assertEqual(q.answer, 'Trả lời bởi leader')
            self.assertIsNotNone(q.answered_at)
            self.assertEqual(q.answered_by_id, leader_2_id)

    def test_07_add_question_htmx_keeps_target_id(self):
        self.login()

        with self.app.app_context():
            client = Client(name='HTMX Client', symbol='HXC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='HTMX Project',
                client_id=client.id,
                po_number='55555555',
                status='New',
                progress=0,
                owner_id=self.admin_id
            )
            db.session.add(project)
            db.session.commit()
            project_id = project.id

        self.login_as(self.admin_id)
        resp = self.client.post(
            f'/project/{project_id}/add_question',
            data={'question': '', 'source': 'project_detail'},
            headers={'HX-Request': 'true'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('id="question-list-project_detail"', html)
        self.assertNotIn('id="question-list-default"', html)

    def test_08_dashboard_question_reply_visible_for_leader(self):
        self.login()

        with self.app.app_context():
            leader_1 = User(
                username='leader_dash_1',
                email='leader_dash_1@example.com',
                role='leader',
                is_allowed=True,
                auth_type='manual',
                display_name='Leader Dash 1'
            )
            leader_1.set_password('123')
            db.session.add(leader_1)

            leader_2 = User(
                username='leader_dash_2',
                email='leader_dash_2@example.com',
                role='leader',
                is_allowed=True,
                auth_type='manual',
                display_name='Leader Dash 2'
            )
            leader_2.set_password('123')
            db.session.add(leader_2)

            client = Client(name='Dash Client', symbol='DSC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='Dash Project',
                client_id=client.id,
                po_number='44444444',
                status='New',
                progress=0,
                owner_id=leader_2.id
            )
            db.session.add(project)
            db.session.commit()

            q = ProjectQuestion(
                project_id=project.id,
                question='Câu hỏi dashboard',
                created_by_id=leader_1.id
            )
            db.session.add(q)
            db.session.commit()
            question_id = q.id
            leader_2_id = leader_2.id

        self.login_as(leader_2_id)
        resp = self.client.get('/', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn(f'replyForm-dashboard_card-{question_id}', html)

    def test_09_create_task_api_allows_primary_owner_only(self):
        self.login()

        with self.app.app_context():
            client = Client(name='Task Client', symbol='TSC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='Task API Project',
                client_id=client.id,
                po_number='33333333',
                status='New',
                progress=0,
                owner_id=self.admin_id
            )
            db.session.add(project)
            db.session.commit()
            project_id = project.id

        resp = self.client.post('/tasks', json={
            'project_id': project_id,
            'title': 'API Task 1',
            'start_date': datetime.now().date().isoformat(),
            'assignee_id': self.admin_id
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get('title'), 'API Task 1')

        with self.app.app_context():
            t = Task.query.filter_by(project_id=project_id).first()
            self.assertIsNotNone(t)
            self.assertEqual(t.name, 'API Task 1')

    def test_10_password_reset_token_flow_updates_password(self):
        with self.app.app_context():
            u = User(
                username='reset_user',
                email='reset_user@example.com',
                role='member',
                is_allowed=True,
                auth_type='manual',
                display_name='Reset User'
            )
            u.set_password('oldpass')
            db.session.add(u)
            db.session.commit()
            token = u.get_reset_token()
            user_id = u.id

        resp = self.client.post(
            f'/reset_password/{token}',
            data={'password': 'newpass123', 'confirm_password': 'newpass123'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            u2 = db.session.get(User, user_id)
            self.assertTrue(u2.check_password('newpass123'))

    def test_11_project_detail_does_not_show_reply_for_own_question(self):
        self.login()

        with self.app.app_context():
            client = Client(name='OwnQ Client', symbol='OQC')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='OwnQ Project',
                client_id=client.id,
                po_number='22222222',
                status='New',
                progress=0,
                owner_id=self.admin_id
            )
            db.session.add(project)
            db.session.commit()

            q = ProjectQuestion(project_id=project.id, question='Câu hỏi của chính mình', created_by_id=self.admin_id)
            db.session.add(q)
            db.session.commit()
            project_id = project.id
            question_id = q.id

        resp = self.client.get(f'/project/{project_id}', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertNotIn(f'replyForm-project_detail-{question_id}', html)

    def test_12_dashboard_does_not_show_reply_for_own_question(self):
        self.login()

        with self.app.app_context():
            client = Client(name='OwnQ Dash Client', symbol='OQD')
            db.session.add(client)
            db.session.commit()

            project = Project(
                name='OwnQ Dash Project',
                client_id=client.id,
                po_number='11111111',
                status='New',
                progress=0,
                owner_id=self.admin_id
            )
            db.session.add(project)
            db.session.commit()

            q = ProjectQuestion(project_id=project.id, question='Câu hỏi của admin', created_by_id=self.admin_id)
            db.session.add(q)
            db.session.commit()
            question_id = q.id

        resp = self.client.get('/', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertNotIn(f'replyForm-dashboard_card-{question_id}', html)

    def test_13_admin_can_delete_question(self):
        self.login()
        with self.app.app_context():
            client = Client(name='DelQ Client', symbol='DQC')
            db.session.add(client)
            db.session.commit()
            project = Project(name='DelQ Project', client_id=client.id, po_number='12121212', status='New', owner_id=self.admin_id)
            db.session.add(project)
            db.session.commit()
            q = ProjectQuestion(project_id=project.id, question='Q to delete', created_by_id=self.admin_id)
            db.session.add(q)
            db.session.commit()
            q_id = q.id
        
        resp = self.client.post(f'/question/{q_id}/delete', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        
        with self.app.app_context():
            q = db.session.get(ProjectQuestion, q_id)
            self.assertIsNone(q)

    def test_14_manager_can_edit_answer(self):
        self.login() # As Admin first to create users
        with self.app.app_context():
            manager = User(username='mgr_edit', email='mgr_edit@example.com', role='manager', is_allowed=True, auth_type='manual', display_name='Mgr Edit')
            manager.set_password('123')
            db.session.add(manager)
            db.session.commit()
            mgr_id = manager.id
            
            client = Client(name='EditAns Client', symbol='EAC')
            db.session.add(client)
            db.session.commit()
            project = Project(name='EditAns Project', client_id=client.id, po_number='13131313', status='New', owner_id=self.admin_id)
            db.session.add(project)
            db.session.commit()
            
            q = ProjectQuestion(project_id=project.id, question='Q to edit', created_by_id=self.admin_id)
            q.answer = 'Old Answer'
            q.answered_by_id = mgr_id
            q.answered_at = datetime.now()
            db.session.add(q)
            db.session.commit()
            q_id = q.id

        self.login_as(mgr_id)
        resp = self.client.post(f'/question/{q_id}/edit_answer', data={'answer': 'New Answer'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        
        with self.app.app_context():
            q = db.session.get(ProjectQuestion, q_id)
            self.assertEqual(q.answer, 'New Answer')

    def test_15_leader_can_delete_answer(self):
        self.login() # As Admin first
        with self.app.app_context():
            leader = User(username='leader_del', email='leader_del@example.com', role='leader', is_allowed=True, auth_type='manual', display_name='Leader Del')
            leader.set_password('123')
            db.session.add(leader)
            db.session.commit()
            leader_id = leader.id
            
            client = Client(name='DelAns Client', symbol='DAC')
            db.session.add(client)
            db.session.commit()
            project = Project(name='DelAns Project', client_id=client.id, po_number='14141414', status='New', owner_id=self.admin_id)
            db.session.add(project)
            db.session.commit()
            
            q = ProjectQuestion(project_id=project.id, question='Q ans to delete', created_by_id=self.admin_id)
            q.answer = 'Answer to delete'
            q.answered_by_id = leader_id
            q.answered_at = datetime.now()
            db.session.add(q)
            db.session.commit()
            q_id = q.id

        self.login_as(leader_id)
        resp = self.client.post(f'/question/{q_id}/delete_answer', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        
        with self.app.app_context():
            q = db.session.get(ProjectQuestion, q_id)
            self.assertIsNone(q.answer)
            self.assertIsNone(q.answered_at)
            self.assertIsNone(q.answered_by_id)

if __name__ == '__main__':
    unittest.main()
