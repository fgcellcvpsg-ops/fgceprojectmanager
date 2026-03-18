import os
import zipfile
import shutil
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required
from app.utils import min_role_required, t

backup_bp = Blueprint('backup', __name__)

def get_backup_dir():
    backup_dir = os.path.join(os.getcwd(), 'backups')
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

def get_db_path():
    return os.path.join(current_app.instance_path, 'projects.db')

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
            backups.append({
                'filename': fn,
                'created_at': datetime.fromtimestamp(st.st_mtime),
                'size': round(st.st_size / 1024, 1)
            })
        except Exception:
            continue
    return render_template('backup.html', backups=backups)


@backup_bp.route('/backup_db', methods=['POST'])
@login_required
@min_role_required('admin')
def backup_db():
    backup_dir = get_backup_dir()
    db_path = get_db_path()
    
    name = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    fp = os.path.join(backup_dir, name)
    try:
        with zipfile.ZipFile(fp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(db_path, arcname='projects.db')
        flash(t('msg_backup_created').format(name=name) if t('msg_backup_created') != 'msg_backup_created' else f"✅ Đã tạo backup: {name}", "success")
    except Exception as e:
        current_app.logger.exception("Backup failed: %s", e)
        flash(t('err_backup_create_failed') if t('err_backup_create_failed') != 'err_backup_create_failed' else "❌ Tạo backup thất bại.", "danger")
        
    return redirect(url_for('backup.list'))


@backup_bp.route('/download_backup/<filename>')
@login_required
@min_role_required('admin')
def download_backup(filename):
    backup_dir = get_backup_dir()
    return send_file(os.path.join(backup_dir, filename), as_attachment=True)


@backup_bp.route('/restore_backup/<filename>', methods=['POST'])
@login_required
@min_role_required('admin')
def restore_backup(filename):
    backup_dir = get_backup_dir()
    db_path = get_db_path()
    
    fp = os.path.join(backup_dir, filename)
    try:
        with zipfile.ZipFile(fp, 'r') as z:
            z.extract('projects.db', current_app.instance_path)
        # Verify if extracted file needs moving (if zip structure was flat, it extracts to instance_path/projects.db)
        # If it was zipped with folder structure, it might be different. 
        # But arcname='projects.db' ensures flat structure.
        
        # In app.py: shutil.copyfile(os.path.join(app.instance_path, 'projects.db'), db_path)
        # Wait, extract already places it in instance_path. 
        # If db_path IS os.path.join(current_app.instance_path, 'projects.db'), then extract overwrites it?
        # app.py logic:
        # z.extract('projects.db', app.instance_path)
        # shutil.copyfile(os.path.join(app.instance_path, 'projects.db'), db_path)
        # If db_path is exactly that file, copyfile to itself might be redundant or fail?
        # Actually in app.py db_path is defined as `os.path.join(app.instance_path, 'projects.db')`.
        # So `z.extract` should be enough if it overwrites.
        # But let's follow app.py logic to be safe, maybe `db_path` was different?
        # In app.py: db_path = os.path.join(app.instance_path, 'projects.db')
        # So z.extract overwrites it.
        
        flash(t('msg_backup_restored') if t('msg_backup_restored') != 'msg_backup_restored' else "♻️ Phục hồi thành công. Khởi động lại ứng dụng.", "success")
    except Exception as e:
        current_app.logger.exception("Restore failed: %s", e)
        flash(t('err_backup_restore_failed') if t('err_backup_restore_failed') != 'err_backup_restore_failed' else "❌ Phục hồi thất bại.", "danger")
        
    return redirect(url_for('backup.list'))


@backup_bp.route('/delete_backup/<filename>', methods=['POST'])
@login_required
@min_role_required('admin')
def delete_backup(filename):
    backup_dir = get_backup_dir()
    try:
        os.remove(os.path.join(backup_dir, filename))
        flash(t('msg_backup_deleted'), "success")
    except Exception as e:
        current_app.logger.exception("Delete backup failed: %s", e)
        flash(t('err_backup_delete_failed'), "danger")
        
    return redirect(url_for('backup.list'))
