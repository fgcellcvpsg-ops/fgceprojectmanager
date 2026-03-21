import csv
from io import StringIO
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.extensions import db
from app.models import User, ActivityLog, Project, WorkHistoryReport
from app.utils import min_role_required, is_valid_email, is_strong_password, t, log_activity

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
@min_role_required('manager')
def admin_users():
    # Manager restriction: cannot see/edit admins is handled by UI hiding, 
    # but backend should also prevent creating admins.
    if current_user.role == 'manager':
        # Managers can access this route to manage members/leaders, but strict check on actions
        pass

    # Helper to fetch users for re-render
    def get_users_list():
        if current_user.role == 'manager':
            return User.query.filter(User.role != 'admin').order_by(User.display_name).all()
        return User.query.order_by(User.display_name).all()

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        if action == 'add_user':
            username = (request.form.get('username') or '').strip().lower()
            email = (request.form.get('email') or '').strip().lower()
            display_name = (request.form.get('display_name') or '').strip()
            role = (request.form.get('role') or 'member').strip()
            password = request.form.get('password') or ''
            confirm = request.form.get('confirm') or ''
            is_allowed = True if request.form.get('is_allowed') in ('on', 'true', '1') else False
            
            error = None
            if not username or not email or not password or not confirm:
                error = t('err_fill_all_fields')
            elif not is_valid_email(email):
                error = t('err_email_format')
            elif not is_strong_password(password):
                error = t('err_password_strength')
            elif password != confirm:
                error = t('err_password_mismatch')
            
            if not error:
                if role not in ('member', 'leader', 'manager', 'admin', 'quotation', 'secretary'):
                    role = 'member'
                # Manager cannot create admin
                if current_user.role == 'manager' and role == 'admin':
                    error = t('err_manager_create_admin')

            if error:
                flash(error, "warning")
                return render_template('admin_users.html', users=get_users_list())

            try:
                u = User(username=username, email=email, display_name=display_name or None, role=role, is_allowed=is_allowed, auth_type='manual')
                u.set_password(password)
                db.session.add(u)
                db.session.commit()
                log_activity('CREATE_USER', details=f'Created user {username}')
                flash(t('msg_user_added'), "success")
                return redirect(url_for('admin.admin_users'))
            except IntegrityError:
                db.session.rollback()
                flash(t('err_user_exists'), "danger")
                return render_template('admin_users.html', users=get_users_list())
            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.exception("add_user error: %s", e)
                flash(t('err_user_add_failed'), "danger")
                return render_template('admin_users.html', users=get_users_list())
        elif action == 'update_user':
            try:
                uid = int(request.form.get('user_id') or '0')
            except Exception:
                uid = 0
            u = db.session.get(User, uid)
            if not u:
                flash(t('err_user_not_found'), "warning")
                return redirect(url_for('admin.admin_users'))
            
            # Manager cannot edit admin
            if current_user.role == 'manager' and u.role == 'admin':
                flash(t('err_manager_edit_admin'), "danger")
                return redirect(url_for('admin.admin_users'))

            display_name = (request.form.get('display_name') or '').strip()
            email = (request.form.get('email') or '').strip().lower()
            role = (request.form.get('role') or 'member').strip()
            is_allowed = True if request.form.get('is_allowed') in ('on', 'true', '1') else False
            
            # Check email validity and uniqueness
            if not email:
                flash(t('err_email_required'), "warning")
                return redirect(url_for('admin.admin_users'))
            if not is_valid_email(email):
                flash(t('err_email_format'), "warning")
                return redirect(url_for('admin.admin_users'))
            
            existing_user = User.query.filter(User.email == email, User.id != u.id).first()
            if existing_user:
                flash(t('err_email_used'), "warning")
                return redirect(url_for('admin.admin_users'))
            
            if role not in ('member', 'leader', 'manager', 'admin', 'quotation', 'secretary'):
                role = 'member'
            
            # Manager cannot promote to admin
            if current_user.role == 'manager' and role == 'admin':
                flash(t('err_manager_promote_admin'), "danger")
                return redirect(url_for('admin.admin_users'))

            # Manager cannot change role of other managers (or themselves)
            if current_user.role == 'manager' and u.role == 'manager':
                role = 'manager'

            # Password change logic
            new_password = (request.form.get('new_password') or '').strip()
            if new_password:
                can_change_pass = False
                if current_user.role == 'admin':
                    can_change_pass = True
                elif current_user.role == 'manager':
                    if u.role in ['leader', 'member']:
                        can_change_pass = True
                
                if not can_change_pass:
                    flash(t('err_password_change_denied'), "danger")
                    return redirect(url_for('admin.admin_users'))

                if uid == current_user.id:
                    current_pw = (request.form.get('current_password') or '')
                    if (not current_pw) or (not u.check_password(current_pw)):
                        flash(t('err_current_password_incorrect'), "danger")
                        return redirect(url_for('admin.admin_users'))

                if not is_strong_password(new_password):
                    flash(t('err_password_strength'), "danger")
                    return redirect(url_for('admin.admin_users'))
                
                u.set_password(new_password)
                flash(t('msg_password_updated'), "success")

            u.display_name = display_name or None
            u.email = email
            u.role = role
            u.is_allowed = is_allowed
            try:
                db.session.commit()
                log_activity('UPDATE_USER', details=f'Updated user {u.username}')
                flash(t('msg_user_updated') if t('msg_user_updated') != 'msg_user_updated' else "✅ Đã cập nhật người dùng.", "success")
            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.exception("update_user error: %s", e)
                flash(t('err_user_update_failed') if t('err_user_update_failed') != 'err_user_update_failed' else "❌ Lỗi khi cập nhật người dùng.", "danger")
            return redirect(url_for('admin.admin_users'))
        elif action == 'delete_user':
            try:
                uid = int(request.form.get('user_id') or '0')
            except Exception:
                uid = 0
            if uid == current_user.id:
                flash(t('err_cannot_delete_self') if t('err_cannot_delete_self') != 'err_cannot_delete_self' else "❌ Không thể xoá tài khoản hiện tại.", "warning")
                return redirect(url_for('admin.admin_users'))
            u = db.session.get(User, uid)
            if not u:
                flash(t('err_user_not_found') if t('err_user_not_found') != 'err_user_not_found' else "Không tìm thấy người dùng.", "warning")
                return redirect(url_for('admin.admin_users'))
            
            # Manager cannot delete admin
            if current_user.role == 'manager' and u.role == 'admin':
                flash(t('err_manager_delete_admin') if t('err_manager_delete_admin') != 'err_manager_delete_admin' else "Manager không thể xóa tài khoản Admin.", "danger")
                return redirect(url_for('admin.admin_users'))

            try:
                db.session.delete(u)
                db.session.commit()
                log_activity('DELETE_USER', details=f'Deleted user {u.username}')
                flash(t('msg_user_deleted') if t('msg_user_deleted') != 'msg_user_deleted' else "🗑️ Đã xoá người dùng.", "success")
            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.exception("delete_user error: %s", e)
                flash(t('err_user_delete_failed') if t('err_user_delete_failed') != 'err_user_delete_failed' else "❌ Lỗi khi xoá người dùng.", "danger")
            return redirect(url_for('admin.admin_users'))
    if current_user.role == 'manager':
        users = User.query.filter(User.role != 'admin').order_by(User.display_name).all()
    else:
        users = User.query.order_by(User.display_name).all()
    return render_template('admin_users.html', users=users)

@admin_bp.route('/admin/users/allowed', methods=['POST'])
@login_required
@min_role_required('admin')
def allowed_users():
    email = (request.form.get('email') or '').strip().lower()
    if not email:
        flash(t('err_email_required'), "warning")
        return redirect(url_for('admin.admin_users'))
    user = User.query.filter(or_(User.username == email, User.email == email)).first()
    if not user:
        flash(t('err_user_not_found'), "warning")
        return redirect(url_for('admin.admin_users'))
    try:
        user.is_allowed = True
        db.session.commit()
        log_activity('APPROVE_USER', details=f'Approved user {user.username}')
        flash(t('msg_login_allowed'), "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("allowed_users error: %s", e)
        flash(t('err_generic'), "error")
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/admin/activity_report')
@login_required
@min_role_required('manager')
def activity_report():
    users = User.query.order_by(User.display_name).all()
    
    query = ActivityLog.query
    
    # Filter by User
    user_id = request.args.get('user_id')
    selected_user_id = None
    if user_id:
        try:
            selected_user_id = int(user_id)
            query = query.filter(ActivityLog.user_id == selected_user_id)
        except ValueError:
            pass
            
    # Filter by Date Range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(ActivityLog.timestamp >= start_date)
        except ValueError:
            pass
            
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Add one day to include the end date fully
            end_date = end_date + timedelta(days=1) 
            query = query.filter(ActivityLog.timestamp < end_date)
        except ValueError:
            pass
            
    # Sort by latest first
    logs = query.order_by(ActivityLog.timestamp.desc()).limit(1000).all()
    
    return render_template('activity_report.html', users=users, logs=logs, selected_user_id=selected_user_id, now=datetime.now())

@admin_bp.route('/admin/work_history_report', methods=['GET', 'POST'])
@login_required
@min_role_required('manager')
def work_history_report():
    projects = Project.query.order_by(Project.name).all()

    if request.method == 'POST':
        work_type = (request.form.get('work_type') or '').strip()
        email_from = (request.form.get('email_from') or '').strip()
        email_to = (request.form.get('email_to') or '').strip()
        change_details = (request.form.get('change_details') or '').strip()
        project_id_raw = (request.form.get('project_id') or '').strip()
        work_date_raw = (request.form.get('work_date') or '').strip()
        work_time_raw = (request.form.get('work_time') or '').strip()

        errors = []
        if not work_type:
            errors.append(t('err_work_type_required'))
        
        # Validate based on work_type
        if work_type == 'Email đến':
            # Không bắt buộc người gửi; nếu trống, đặt rỗng để tránh NULL
            if not email_from:
                email_from = ''
            # Auto-fill recipient as current user if not provided
            if not email_to:
                email_to = current_user.email
        elif work_type == 'Email đi':
            if not email_to:
                errors.append(t('err_email_to_required'))
            # Auto-fill sender as current user if not provided
            if not email_from:
                email_from = current_user.email
        
        if not project_id_raw:
            errors.append(t('err_project_required'))
        if not change_details:
            errors.append(t('err_change_details_required'))

        project = None
        if project_id_raw:
            try:
                project_id = int(project_id_raw)
                project = db.session.get(Project, project_id)
            except Exception:
                project = None
            if not project:
                errors.append(t('err_project_not_found'))

        if errors:
            for msg in errors:
                flash(msg, 'warning')
            return redirect(url_for('admin.work_history_report'))

        work_date = None
        if work_date_raw:
            try:
                work_date = datetime.strptime(work_date_raw, '%Y-%m-%d').date()
            except ValueError:
                work_date = None
        if not work_date:
            work_date = datetime.now().date()

        entry = WorkHistoryReport(
            work_type=work_type,
            email_from=email_from,
            email_to=email_to,
            change_details=change_details,
            project_id=project.id,
            work_date=work_date,
            work_time=work_time_raw,
            created_by_id=current_user.id,
        )
        try:
            db.session.add(entry)
            db.session.commit()
            flash(t('msg_work_history_added'), 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception("work_history_report create error: %s", e)
            flash(t('err_generic'), 'danger')
        return redirect(url_for('admin.work_history_report'))

    query = WorkHistoryReport.query.options(
        joinedload(WorkHistoryReport.project),
        joinedload(WorkHistoryReport.created_by),
    )

    view_by = request.args.get('view_by', 'entry')

    project_id = request.args.get('project_id')
    if project_id:
        try:
            query = query.filter(WorkHistoryReport.project_id == int(project_id))
        except ValueError:
            pass

    work_type = (request.args.get('work_type') or '').strip()
    if work_type:
        query = query.filter(WorkHistoryReport.work_type.ilike(f"%{work_type}%"))

    email_from = (request.args.get('email_from') or '').strip()
    if email_from:
        parts = [p.strip() for p in email_from.replace(';', ',').split(',') if p.strip()]
        if len(parts) > 1:
            ors = [WorkHistoryReport.email_from.ilike(f"%{p}%") for p in parts]
            query = query.filter(or_(*ors))
        else:
            query = query.filter(WorkHistoryReport.email_from.ilike(f"%{email_from}%"))

    email_to = (request.args.get('email_to') or '').strip()
    if email_to:
        parts = [p.strip() for p in email_to.replace(';', ',').split(',') if p.strip()]
        if len(parts) > 1:
            ors = [WorkHistoryReport.email_to.ilike(f"%{p}%") for p in parts]
            query = query.filter(or_(*ors))
        else:
            query = query.filter(WorkHistoryReport.email_to.ilike(f"%{email_to}%"))

    project_name = (request.args.get('project_name') or '').strip()
    if project_name:
        like = f"%{project_name}%"
        query = query.join(WorkHistoryReport.project).filter(Project.name.ilike(like))

    search_text = (request.args.get('search_text') or '').strip()
    if search_text:
        like = f"%{search_text}%"
        query = query.join(WorkHistoryReport.project).filter(or_(
            WorkHistoryReport.change_details.ilike(like),
            WorkHistoryReport.work_type.ilike(like),
            WorkHistoryReport.email_from.ilike(like),
            WorkHistoryReport.email_to.ilike(like),
            Project.name.ilike(like)
        ))

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    quick = (request.args.get('quick') or '').strip()
    if quick == 'today':
        today = datetime.now().strftime('%Y-%m-%d')
        start_date_str = start_date_str or today
        end_date_str = end_date_str or today
    elif quick == 'this_week':
        now = datetime.now()
        start_of_week = now - timedelta(days=now.weekday())
        start_date_str = start_date_str or start_of_week.strftime('%Y-%m-%d')
        end_date_str = end_date_str or now.strftime('%Y-%m-%d')
    elif quick == 'this_month':
        now = datetime.now()
        start_of_month = now.replace(day=1)
        start_date_str = start_date_str or start_of_month.strftime('%Y-%m-%d')
        end_date_str = end_date_str or now.strftime('%Y-%m-%d')
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(WorkHistoryReport.work_date >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(WorkHistoryReport.work_date <= end_date)
        except ValueError:
            pass

    entries = query.order_by(WorkHistoryReport.created_at.desc()).limit(2000).all()
    filters = request.args.to_dict(flat=True)
    filters.setdefault('view_by', view_by)
    return render_template(
        'work_history_report.html',
        entries=entries,
        projects=projects,
        filters=filters,
        now=datetime.now(),
    )


@admin_bp.route('/admin/work_history_report/export.csv')
@login_required
@min_role_required('manager')
def work_history_report_export_csv():
    query = WorkHistoryReport.query.options(
        joinedload(WorkHistoryReport.project),
        joinedload(WorkHistoryReport.created_by),
    )

    project_id = request.args.get('project_id')
    if project_id:
        try:
            query = query.filter(WorkHistoryReport.project_id == int(project_id))
        except ValueError:
            pass

    work_type = (request.args.get('work_type') or '').strip()
    if work_type:
        query = query.filter(WorkHistoryReport.work_type.ilike(f"%{work_type}%"))

    email_from = (request.args.get('email_from') or '').strip()
    if email_from:
        parts = [p.strip() for p in email_from.replace(';', ',').split(',') if p.strip()]
        if len(parts) > 1:
            ors = [WorkHistoryReport.email_from.ilike(f"%{p}%") for p in parts]
            query = query.filter(or_(*ors))
        else:
            query = query.filter(WorkHistoryReport.email_from.ilike(f"%{email_from}%"))

    email_to = (request.args.get('email_to') or '').strip()
    if email_to:
        parts = [p.strip() for p in email_to.replace(';', ',').split(',') if p.strip()]
        if len(parts) > 1:
            ors = [WorkHistoryReport.email_to.ilike(f"%{p}%") for p in parts]
            query = query.filter(or_(*ors))
        else:
            query = query.filter(WorkHistoryReport.email_to.ilike(f"%{email_to}%"))

    project_name = (request.args.get('project_name') or '').strip()
    if project_name:
        like = f"%{project_name}%"
        query = query.join(WorkHistoryReport.project).filter(Project.name.ilike(like))

    search_text = (request.args.get('search_text') or '').strip()
    if search_text:
        like = f"%{search_text}%"
        query = query.join(WorkHistoryReport.project).filter(or_(
            WorkHistoryReport.change_details.ilike(like),
            WorkHistoryReport.work_type.ilike(like),
            WorkHistoryReport.email_from.ilike(like),
            WorkHistoryReport.email_to.ilike(like),
            Project.name.ilike(like)
        ))

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(WorkHistoryReport.created_at >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(WorkHistoryReport.created_at < end_date)
        except ValueError:
            pass

    rows = query.order_by(WorkHistoryReport.created_at.desc()).limit(5000).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Work Date',
        'Created At',
        'Work Type',
        'Email From',
        'Email To',
        'Project',
        'Changes',
        'Entered By',
    ])
    for r in rows:
        writer.writerow([
            (r.work_date.strftime('%Y-%m-%d') if r.work_date else ''),
            (r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else ''),
            r.work_type or '',
            r.email_from or '',
            r.email_to or '',
            (r.project.name if r.project else ''),
            (r.change_details or ''),
            (r.created_by.display_name if r.created_by else ''),
        ])

    csv_text = '\ufeff' + output.getvalue()
    filename = f"work_history_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response = Response(csv_text, mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
