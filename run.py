import os
import sys
import time
import traceback

# Keep window open on crash even before imports
# def crash_handler(type, value, tb):
#     print("\n❌ UNCAUGHT EXCEPTION:", file=sys.stderr)
#     traceback.print_exception(type, value, tb)
#     print("\nPress Enter to exit...")
#     # input()

# sys.excepthook = crash_handler

print("Starting run.py...")
try:
    import secrets
    import webbrowser
    import threading
    import multiprocessing
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    from app import create_app
    from app.extensions import db
    from app.models import User
    from werkzeug.security import generate_password_hash

    # Expose 'app' for Gunicorn to import
    app = create_app()

    def get_port():
        try:
            return int(os.getenv("PORT", "5000"))
        except Exception:
            return 5000

    def open_browser():
        """Wait for server to start then open browser"""
        time.sleep(2.0)
        port = get_port()
        url = f"http://localhost:{port}"
        print(f"Opening browser at {url} ...")
        webbrowser.open(url)

    if __name__ == "__main__":
        # PyInstaller multiprocessing fix for Windows
        multiprocessing.freeze_support()

        try:
            with app.app_context():
                db.create_all()
                # Seed admin only when explicitly allowed via environment variables
                if os.getenv("ALLOW_SEED_ADMIN") == "true":
                    if not User.query.filter_by(username="admin").first():
                        pwd = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
                        admin = User(
                            username="admin",
                            email=os.getenv("ADMIN_EMAIL") or "admin@example.com",
                            display_name="Administrator",
                            role="admin",
                            auth_type="manual",
                            is_allowed=True
                        )
                        admin.password_hash = generate_password_hash(pwd)
                        db.session.add(admin)
                        db.session.commit()
                        print("✅ Admin user created: admin")
                        print("Admin password (printed once):", pwd)
                        print("Please change the password immediately after first login.")
                else:
                    print("Admin seeding skipped. To seed admin set ALLOW_SEED_ADMIN=true and optionally ADMIN_PASSWORD.")
            
            # Run development server
            print(f"Server Instance Path: {app.instance_path}")
            print(f"Server DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
            
            # Open browser in a separate thread
            if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
                # Only open browser on the main process, not the reloader
                threading.Thread(target=open_browser, daemon=True).start()

            # host='0.0.0.0' allows access from other computers on the same network
            # Disable debug mode in production/exe to avoid reloader issues
            # In exe, FLASK_DEBUG should default to False
            is_debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
            
            # FORCE debug=False if running as PyInstaller executable to prevent reloader
            if getattr(sys, 'frozen', False):
                is_debug = False
                print("Running in Frozen mode (EXE). Debug mode disabled.")

            # Force debug=True for troubleshooting, but disable reloader to avoid process issues
            # is_debug = True
            app.run(host='0.0.0.0', debug=is_debug, port=get_port(), use_reloader=False)

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: {e}")
            traceback.print_exc()
        finally:
            print("\nApplication stopped.")
            # input()

except Exception as e:
    print(f"\n❌ IMPORT ERROR: {e}")
    traceback.print_exc()
    print("\nPress Enter to exit...")
    # input()
