import base64
import decimal
import json
import os
import tempfile
import threading
import zipfile
from datetime import date, datetime
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for, current_app
from flask_login import login_required
from sqlalchemy import MetaData, Table, inspect, insert, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from app.extensions import db
from app.utils import min_role_required, t

backup_bp = Blueprint('backup', __name__)
_backup_lock = threading.Lock()
_backup_running = False

def get_backup_dir():
    backup_dir = os.getenv('BACKUP_DIR') or os.path.join(current_app.instance_path, 'backups')
    try:
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir
    except Exception:
        fallback = os.path.join(tempfile.gettempdir(), 'fgce_backups')
        os.makedirs(fallback, exist_ok=True)
        return fallback

def _safe_join(base_dir, filename):
    if not filename:
        raise ValueError("Invalid filename")
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise ValueError("Invalid filename")
    full_path = os.path.abspath(os.path.join(base_dir, safe_name))
    base_abs = os.path.abspath(base_dir)
    if not full_path.startswith(base_abs + os.sep):
        raise ValueError("Invalid filename")
    return full_path

def _current_db_uri():
    return current_app.config.get('SQLALCHEMY_DATABASE_URI') or os.getenv('DATABASE_URL') or ''

def _sqlite_db_path(db_uri):
    url = make_url(db_uri)
    if url.drivername != 'sqlite':
        return None
    db_file = url.database
    if not db_file:
        return None
    if os.path.isabs(db_file):
        return db_file
    return os.path.join(os.getcwd(), db_file)

def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode('ascii')
    return str(value)

def _infer_and_cast(table, record):
    for col in table.columns:
        if col.name not in record:
            continue
        v = record[col.name]
        if v is None:
            continue
        try:
            py_type = col.type.python_type
        except Exception:
            continue
        if isinstance(v, py_type):
            continue
        try:
            if py_type is datetime and isinstance(v, str):
                record[col.name] = datetime.fromisoformat(v)
            elif py_type is date and isinstance(v, str):
                record[col.name] = date.fromisoformat(v)
            elif py_type is bool and isinstance(v, str):
                record[col.name] = v.lower() in ('1', 'true', 'yes', 'y', 'on')
            elif py_type is int and isinstance(v, str):
                record[col.name] = int(v)
            elif py_type is float and isinstance(v, str):
                record[col.name] = float(v)
            elif py_type is decimal.Decimal and isinstance(v, str):
                record[col.name] = decimal.Decimal(v)
        except Exception:
            continue
    return record

def _toposort_tables(tables, inspector):
    deps = {t: set() for t in tables}
    for t in tables:
        try:
            fks = inspector.get_foreign_keys(t) or []
        except Exception:
            fks = []
        for fk in fks:
            ref = fk.get('referred_table')
            if ref and ref in deps and ref != t:
                deps[t].add(ref)

    ordered = []
    ready = [t for t, d in deps.items() if not d]
    ready.sort()
    while ready:
        n = ready.pop(0)
        ordered.append(n)
        for m in list(deps.keys()):
            if n in deps[m]:
                deps[m].remove(n)
                if not deps[m] and m not in ordered and m not in ready:
                    ready.append(m)
                    ready.sort()

    remaining = [t for t in tables if t not in ordered]
    remaining.sort()
    return ordered + remaining

def _create_postgres_backup_zip(app, backup_dir, final_path):
    global _backup_running
    try:
        with app.app_context():
            engine = db.engine
            inspector = inspect(engine)
            meta = MetaData()
            table_names = [t for t in inspector.get_table_names() if t != 'alembic_version']

            with tempfile.TemporaryDirectory(dir=backup_dir) as tmp_dir:
                tables_dir = os.path.join(tmp_dir, 'tables')
                os.makedirs(tables_dir, exist_ok=True)
                manifest = {
                    'created_at': datetime.utcnow().isoformat() + 'Z',
                    'dialect': engine.dialect.name,
                    'tables': table_names,
                }
                with open(os.path.join(tmp_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)

                for table_name in table_names:
                    table = Table(table_name, meta, autoload_with=engine)
                    out_path = os.path.join(tables_dir, f"{table_name}.jsonl")
                    with open(out_path, 'w', encoding='utf-8') as f:
                        attempt = 0
                        while True:
                            try:
                                rows = db.session.execute(select(table).execution_options(stream_results=True)).mappings()
                                for row in rows:
                                    f.write(json.dumps(dict(row), ensure_ascii=False, default=_json_default))
                                    f.write("\n")
                                break
                            except OperationalError:
                                attempt += 1
                                try:
                                    db.session.rollback()
                                except Exception:
                                    pass
                                if attempt >= 2:
                                    raise

                tmp_zip = final_path + '.tmp'
                with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.write(os.path.join(tmp_dir, 'manifest.json'), arcname='manifest.json')
                    for table_name in table_names:
                        z.write(os.path.join(tables_dir, f"{table_name}.jsonl"), arcname=f"tables/{table_name}.jsonl")
                os.replace(tmp_zip, final_path)
    except Exception:
        try:
            current_app.logger.exception("Backup background task failed")
        except Exception:
            pass
        try:
            tmp_zip = final_path + '.tmp'
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
        except Exception:
            pass
    finally:
        try:
            db.session.remove()
        except Exception:
            pass
        with _backup_lock:
            _backup_running = False

@backup_bp.route('/backup', endpoint='list')
@login_required
@min_role_required('admin')
def backup_list():
    backup_dir = get_backup_dir()
    backups = []
    for fn in sorted(os.listdir(backup_dir)):
        fp = os.path.join(backup_dir, fn)
        try:
            st = os.stat(fp)
            size_bytes = int(st.st_size)
            size_display = f"{size_bytes} B" if size_bytes < 1024 else f"{round(size_bytes / 1024, 1)} KB"
            backups.append({
                'filename': fn,
                'created_at': datetime.fromtimestamp(st.st_mtime),
                'size_bytes': size_bytes,
                'size_display': size_display,
            })
        except Exception:
            continue
    return render_template('backup.html', backups=backups)


@backup_bp.route('/backup_db', methods=['GET', 'POST'])
@login_required
@min_role_required('admin')
def backup_db():
    if request.method == 'GET':
        flash("Vui lòng dùng nút tạo backup (POST).", "warning")
        return redirect(url_for('backup.list'))

    backup_dir = get_backup_dir()
    db_uri = _current_db_uri()

    name = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    fp = os.path.join(backup_dir, name)
    try:
        sqlite_path = _sqlite_db_path(db_uri)
        if sqlite_path and os.path.exists(sqlite_path):
            with zipfile.ZipFile(fp, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(sqlite_path, arcname=os.path.basename(sqlite_path))
        else:
            with _backup_lock:
                global _backup_running
                if _backup_running:
                    flash("Backup đang chạy, vui lòng chờ hoàn tất.", "warning")
                    return redirect(url_for('backup.list'))
                _backup_running = True

            app_obj = current_app._get_current_object()
            t_worker = threading.Thread(
                target=_create_postgres_backup_zip,
                args=(app_obj, backup_dir, fp),
                daemon=True,
            )
            t_worker.start()

            flash("⏳ Đã bắt đầu tạo backup. Vui lòng đợi và tải lại trang sau vài phút.", "info")
            return redirect(url_for('backup.list'))

        if not os.path.exists(fp) or os.path.getsize(fp) < 100:
            raise RuntimeError("Backup file is empty")

        msg_tpl = t('msg_backup_created')
        msg = msg_tpl + name if msg_tpl != 'msg_backup_created' else f"✅ Đã tạo backup: {name}"
        flash(msg, "success")
    except Exception as e:
        current_app.logger.exception("Backup failed: %s", e)
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
        err = t('err_backup_failed')
        flash(err if err != 'err_backup_failed' else "❌ Tạo backup thất bại.", "danger")

    return redirect(url_for('backup.list'))


@backup_bp.route('/download_backup/<filename>')
@login_required
@min_role_required('admin')
def download_backup(filename):
    backup_dir = get_backup_dir()
    fp = _safe_join(backup_dir, filename)
    return send_file(fp, as_attachment=True)


@backup_bp.route('/restore_backup/<filename>', methods=['POST'])
@login_required
@min_role_required('admin')
def restore_backup(filename):
    backup_dir = get_backup_dir()
    fp = _safe_join(backup_dir, filename)
    db_uri = _current_db_uri()
    try:
        with zipfile.ZipFile(fp, 'r') as z:
            sqlite_path = _sqlite_db_path(db_uri)
            if sqlite_path:
                arc_candidates = [n for n in z.namelist() if n.endswith('.db')]
                if not arc_candidates:
                    raise RuntimeError("No database file found in backup")
                arcname = arc_candidates[0]
                os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
                with tempfile.TemporaryDirectory(dir=backup_dir) as tmp_dir:
                    extracted = z.extract(arcname, tmp_dir)
                    os.replace(extracted, sqlite_path)
            else:
                names = z.namelist()
                table_files = [n for n in names if n.startswith('tables/') and n.endswith('.jsonl')]
                if not table_files:
                    raise RuntimeError("Invalid backup format")

                engine = db.engine
                inspector = inspect(engine)
                meta = MetaData()
                restore_tables = [os.path.splitext(os.path.basename(n))[0] for n in table_files]
                existing_tables = set(inspector.get_table_names())
                restore_tables = [t for t in restore_tables if t in existing_tables and t != 'alembic_version']
                restore_tables = _toposort_tables(restore_tables, inspector)

                quoted = ", ".join([f"\"{t}\"" for t in restore_tables])
                if engine.dialect.name == 'postgresql' and quoted:
                    db.session.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
                    db.session.commit()

                for table_name in restore_tables:
                    table = Table(table_name, meta, autoload_with=engine)
                    member_name = f"tables/{table_name}.jsonl"
                    with z.open(member_name) as f:
                        batch = []
                        for raw in f:
                            rec = json.loads(raw.decode('utf-8'))
                            rec = _infer_and_cast(table, rec)
                            batch.append(rec)
                            if len(batch) >= 500:
                                db.session.execute(insert(table), batch)
                                batch = []
                        if batch:
                            db.session.execute(insert(table), batch)
                    db.session.commit()

                if engine.dialect.name == 'postgresql':
                    for table_name in restore_tables:
                        table = Table(table_name, meta, autoload_with=engine)
                        if 'id' in table.c:
                            db.session.execute(
                                text(
                                    f"SELECT setval(pg_get_serial_sequence(:tname, 'id'), "
                                    f"(SELECT COALESCE(MAX(id), 1) FROM \"{table_name}\"), true)"
                                ),
                                {'tname': table_name},
                            )
                    db.session.commit()

        msg = t('msg_restore_success')
        flash(msg if msg != 'msg_restore_success' else "♻️ Phục hồi thành công. Khởi động lại ứng dụng.", "success")
    except Exception as e:
        current_app.logger.exception("Restore failed: %s", e)
        err = t('err_restore_failed')
        flash(err if err != 'err_restore_failed' else "❌ Phục hồi thất bại.", "danger")

    return redirect(url_for('backup.list'))


@backup_bp.route('/delete_backup/<filename>', methods=['POST'])
@login_required
@min_role_required('admin')
def delete_backup(filename):
    backup_dir = get_backup_dir()
    try:
        os.remove(_safe_join(backup_dir, filename))
        flash(t('msg_backup_deleted'), "success")
    except Exception as e:
        current_app.logger.exception("Delete backup failed: %s", e)
        flash(t('err_backup_delete_failed'), "danger")
        
    return redirect(url_for('backup.list'))
