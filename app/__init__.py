import os
import logging
from datetime import date, timedelta
from flask import Flask, render_template, request
from sqlalchemy import inspect
from app.extensions import db, login_manager, migrate, csrf, oauth, limiter
from app.models import User, Project, Client, History, Task, ProjectOwner, ActivityLog, WorkHistoryReport
from app.utils import t, get_lang, format_date, project_title, format_code, TRANSLATIONS

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'dev-secret-key'
    
    # Security: Cookie Configuration
    # Only enable Secure cookies if explicitly set or if not in debug mode (assuming prod usually has https)
    # For local dev without HTTPS, keep False.
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    db_path = os.getenv('DATABASE_PATH') or os.path.join(app.instance_path, 'data', 'projects.db')
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    # Ensure correct URI format for Windows
    db_uri_path = db_path.replace('\\', '/')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') or f"sqlite:///{db_uri_path}"
    
    print(f"DEBUG: Instance Path: {app.instance_path}")
    print(f"DEBUG: DB Path: {db_path}")
    print(f"DEBUG: DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    if config_class:
        app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    # oauth.init_app(app) # Configure OAuth if needed

    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user

    # Context processors
    @app.context_processor
    def inject_globals():
        return dict(
            t=t,
            get_lang=get_lang,
            current_lang=get_lang(),
            format_date=format_date,
            project_title=project_title,
            format_code=format_code,
            TRANSLATIONS=TRANSLATIONS,
            today=date.today(),
            timedelta=timedelta
        )

    # Register filters
    app.jinja_env.filters['project_title'] = project_title
    app.jinja_env.filters['format_code'] = format_code
    app.jinja_env.filters['format_date'] = format_date

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.clients import clients_bp
    from app.routes.admin import admin_bp
    from app.routes.projects import projects_bp
    from app.routes.tasks import tasks_bp
    from app.routes.backup import backup_bp
    from app.routes.export import export_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(export_bp)

    # Error handlers
    @app.errorhandler(400)
    def handle_bad_request(e):
        app.logger.warning("400 Bad Request: %s", getattr(e, 'description', str(e)))
        return render_template('400.html', message=getattr(e, 'description', 'Bad Request')), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def handle_server_error(e):
        app.logger.error("500 Server Error: %s", e)
        return render_template('500.html', error=e), 500

    # Create indexes on startup (optional, or move to a command)
    with app.app_context():
        create_indexes(app)

    # Security Headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    return app

def create_indexes(app):
    try:
        # CREATE INDEX IF NOT EXISTS works on modern SQLite and Postgres
        with app.app_context():
            # Check if table exists first to avoid error during init if db not created
            inspector = inspect(db.engine)
            if 'work_history_report' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('work_history_report')]
                if 'work_date' not in cols:
                    db.session.execute(db.text("ALTER TABLE work_history_report ADD COLUMN work_date DATE"))
                if 'work_time' not in cols:
                    db.session.execute(db.text("ALTER TABLE work_history_report ADD COLUMN work_time VARCHAR(20)"))
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_work_history_report_work_date ON work_history_report(work_date);"))
                db.session.commit()
            if 'project' in inspector.get_table_names():
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_project_deadline ON project(deadline);"))
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_project_status ON project(status);"))
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_project_owner_id ON project(owner_id);"))
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_project_client_id ON project(client_id);"))
                db.session.commit()
    except Exception as e:
        app.logger.exception("Tạo index thất bại: %s", e)
