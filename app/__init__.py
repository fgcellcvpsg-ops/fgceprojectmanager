import os
import logging
import traceback
import hashlib
from urllib.parse import urlsplit, urlunsplit
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_wtf.csrf import CSRFError
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from app.extensions import db, login_manager, migrate, csrf, oauth, limiter, mail
from app.models import User, Project, Client, History, Task, ProjectOwner, ActivityLog, WorkHistoryReport
from app.utils import t, get_lang, format_date, project_title, format_code, TRANSLATIONS

def _redact_db_uri(uri: str) -> str:
    if not uri:
        return ""
    try:
        parsed = urlsplit(uri)
        if not parsed.scheme or not parsed.netloc:
            return uri
        if parsed.scheme.startswith("sqlite"):
            return uri
        netloc = parsed.netloc
        if "@" not in netloc:
            return uri
        userinfo, hostport = netloc.rsplit("@", 1)
        if ":" in userinfo:
            user, _pw = userinfo.split(":", 1)
            userinfo_redacted = f"{user}:***"
        else:
            userinfo_redacted = userinfo
        return urlunsplit((parsed.scheme, f"{userinfo_redacted}@{hostport}", parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return uri

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Configuration
    is_debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.config['DEBUG'] = is_debug
    app.config['PROPAGATE_EXCEPTIONS'] = is_debug
    
    # Mail Configuration
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))
    
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
    database_url = os.getenv('DATABASE_URL')

    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        seed = database_url or db_uri_path or app.instance_path
        secret_key = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    app.config['SECRET_KEY'] = secret_key

    app.config['BUILD_VERSION'] = (
        os.getenv("APP_VERSION")
        or os.getenv("BUILD_VERSION")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_SHA")
        or "local"
    )
    
    # Render provides 'postgres://' but SQLAlchemy 1.4+ requires 'postgresql://'
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    # Ensure SSL for PostgreSQL connections (Render requires SSL)
    if database_url and database_url.startswith("postgresql://") and "?" not in database_url:
        database_url += "?sslmode=require"
        
    # --- AUTO FIX DATABASE ON STARTUP ---
    try:
        from app.auto_fix_db import auto_fix_database
        auto_fix_database(database_url or f"sqlite:///{db_uri_path}")
    except Exception as e:
        print(f"Auto fix error: {e}")
    # ------------------------------------
        
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f"sqlite:///{db_uri_path}"

    db_uri = app.config['SQLALCHEMY_DATABASE_URI'] or ''
    if db_uri.startswith('postgresql://') or db_uri.startswith('postgresql+psycopg2://'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '280')),
            'pool_size': int(os.getenv('DB_POOL_SIZE', '5')),
            'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '2')),
            'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
        }
    
    # print(f"DEBUG: Instance Path: {app.instance_path}")
    # print(f"DEBUG: DB Path: {db_path}")
    # print(f"DEBUG: DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

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
    mail.init_app(app)
    # oauth.init_app(app) # Configure OAuth if needed

    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except OperationalError:
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

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
            timedelta=timedelta,
            build_version=app.config.get('BUILD_VERSION', ''),
            db_uri_redacted=_redact_db_uri(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
        )

    # Register filters
    app.jinja_env.filters['project_title'] = project_title
    app.jinja_env.filters['format_code'] = format_code
    app.jinja_env.filters['format_date'] = format_date

    @app.after_request
    def add_no_cache_headers(resp):
        try:
            if resp.mimetype == 'text/html':
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
        except Exception:
            pass
        return resp

    # Handle Unauthorized (401) for HTMX
    @login_manager.unauthorized_handler
    def handle_unauthorized():
        if request.headers.get('HX-Request'):
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = url_for('auth.login', next=request.url)
            return resp
        return redirect(url_for('auth.login', next=request.url))

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
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        app.logger.warning("CSRF Error: %s", getattr(e, 'description', str(e)))
        flash(t('err_csrf_expired') if t('err_csrf_expired') != 'err_csrf_expired' else "Phiên làm việc đã hết hạn hoặc token không hợp lệ. Vui lòng tải lại trang và thử lại.", "warning")
        target = request.referrer or url_for('main.dashboard')
        if request.headers.get('HX-Request'):
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = target
            return resp
        return redirect(target)

    @app.errorhandler(400)
    def handle_bad_request(e):
        app.logger.warning("400 Bad Request: %s", getattr(e, 'description', str(e)))
        if request.headers.get('HX-Request'):
            flash(t('err_bad_request').format(desc=getattr(e, 'description', 'Bad Request')) if t('err_bad_request') != 'err_bad_request' else f"Yêu cầu không hợp lệ: {getattr(e, 'description', 'Bad Request')}", "warning")
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = request.referrer or url_for('main.dashboard')
            return resp
        return render_template('400.html', message=getattr(e, 'description', 'Bad Request')), 400

    @app.errorhandler(403)
    def handle_forbidden(e):
        app.logger.warning("403 Forbidden: %s", getattr(e, 'description', str(e)))
        if request.headers.get('HX-Request'):
            flash(t('err_forbidden') if t('err_forbidden') != 'err_forbidden' else "Bạn không có quyền thực hiện thao tác này.", "danger")
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = request.referrer or url_for('main.dashboard')
            return resp
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def handle_not_found(e):
        if request.headers.get('HX-Request'):
            flash(t('err_not_found') if t('err_not_found') != 'err_not_found' else "Không tìm thấy tài nguyên yêu cầu.", "warning")
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = request.referrer or url_for('main.dashboard')
            return resp
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def handle_server_error(e):
        # Capture full traceback
        error_trace = traceback.format_exc()
        app.logger.error("500 Server Error: %s\n%s", e, error_trace)
        
        # Also print to stdout to ensure it appears in Render logs
        print(f"CRITICAL ERROR TRACEBACK:\n{error_trace}", flush=True)

        if request.headers.get('HX-Request'):
            flash(t('err_server_error') if t('err_server_error') != 'err_server_error' else "Đã xảy ra lỗi máy chủ nội bộ. Vui lòng thử lại sau.", "danger")
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = request.referrer or url_for('main.dashboard')
            return resp
        return render_template('500.html', error=e, error_trace=error_trace), 500

    # Create indexes on startup (optional, or move to a command)
    # with app.app_context():
    #     create_indexes(app)

    # Security Headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    try:
        with app.app_context():
            db.create_all()
            if os.getenv("ALLOW_SEED_ADMIN", "false").lower() == "true":
                admin_password = os.getenv("ADMIN_PASSWORD")
                if admin_password:
                    admin_username = (os.getenv("ADMIN_USERNAME") or "admin").strip().lower()
                    admin_email = (os.getenv("ADMIN_EMAIL") or "admin@example.com").strip().lower()
                    existing = User.query.filter_by(username=admin_username).first()
                    if not existing:
                        admin = User(
                            username=admin_username,
                            email=admin_email,
                            display_name="Administrator",
                            role="admin",
                            auth_type="manual",
                            is_allowed=True
                        )
                        admin.set_password(admin_password)
                        db.session.add(admin)
                        db.session.commit()
                else:
                    app.logger.error("ALLOW_SEED_ADMIN=true nhưng thiếu ADMIN_PASSWORD")
    except Exception as e:
        app.logger.exception("Bootstrap DB/User lỗi: %s", e)

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
