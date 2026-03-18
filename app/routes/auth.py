from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
import time
import os
from ..models import User
from ..extensions import db, limiter, mail
from flask_mail import Message
from app.utils import t, log_activity

import logging
import sys

auth_bp = Blueprint('auth', __name__)

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message(t('msg_reset_password_subject') if t('msg_reset_password_subject') != 'msg_reset_password_subject' else 'Yêu cầu đặt lại mật khẩu',
                  recipients=[user.email])
    reset_url = url_for('auth.reset_token', token=token, _external=True)
    msg_body = t('msg_reset_password_body') if t('msg_reset_password_body') != 'msg_reset_password_body' else f'''Để đặt lại mật khẩu của bạn, vui lòng truy cập vào đường dẫn sau:\n{reset_url}\n\nNếu bạn không yêu cầu thay đổi mật khẩu, vui lòng bỏ qua email này.\n'''
    if t('msg_reset_password_body') != 'msg_reset_password_body':
        msg.body = msg_body.format(reset_url=reset_url)
    else:
        msg.body = msg_body
    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.exception("Lỗi khi gửi email reset mật khẩu: %s", e)

@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)
            flash(t('msg_reset_email_sent') if t('msg_reset_email_sent') != 'msg_reset_email_sent' else 'Một email đã được gửi kèm theo hướng dẫn để đặt lại mật khẩu của bạn.', 'info')
            return redirect(url_for('auth.login'))
        else:
            flash(t('err_account_not_found') if t('err_account_not_found') != 'err_account_not_found' else 'Không tìm thấy tài khoản với email này.', 'danger')
    return render_template('reset_request.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    user = User.verify_reset_token(token)
    if not user:
        flash(t('err_invalid_token') if t('err_invalid_token') != 'err_invalid_token' else 'Token không hợp lệ hoặc đã hết hạn.', 'warning')
        return redirect(url_for('auth.reset_request'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not password or not confirm_password:
            flash(t('err_fill_all_fields') if t('err_fill_all_fields') != 'err_fill_all_fields' else 'Vui lòng nhập đầy đủ thông tin.', 'warning')
            return redirect(url_for('auth.reset_token', token=token))
        if password != confirm_password:
            flash(t('err_password_mismatch') if t('err_password_mismatch') != 'err_password_mismatch' else 'Mật khẩu không khớp.', 'warning')
            return redirect(url_for('auth.reset_token', token=token))
        
        user.set_password(password)
        db.session.commit()
        flash(t('msg_password_updated') if t('msg_password_updated') != 'msg_password_updated' else 'Mật khẩu của bạn đã được cập nhật! Bây giờ bạn có thể đăng nhập.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_token.html', token=token)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        try:
            identifier = (request.form.get('username') or '').strip().lower()
            password = request.form.get('password') or ''
            
            user = User.query.filter(or_(User.username == identifier, User.email == identifier)).first()
            
            if user:
                check = user.check_password(password)
                
                if user.auth_type != 'google' and check:
                    if not user.is_allowed:
                        flash(t('err_account_not_allowed') if t('err_account_not_allowed') != 'err_account_not_allowed' else "❌ Tài khoản chưa được phép đăng nhập.", "error")
                        return redirect(url_for('auth.login'))
                    login_user(user)
                    log_activity('LOGIN', details='Logged in successfully')
                    flash(t('msg_login_success') if t('msg_login_success') != 'msg_login_success' else "✅ Đăng nhập thành công!", "success")
                    return redirect(url_for('main.dashboard'))
            
            flash(t('err_invalid_credentials') if t('err_invalid_credentials') != 'err_invalid_credentials' else "❌ Sai tài khoản hoặc mật khẩu.", "error")
        except Exception as e:
            current_app.logger.exception("Login error: %s", e)
            flash(t('err_login_failed') if t('err_login_failed') != 'err_login_failed' else "❌ Lỗi đăng nhập. Vui lòng thử lại.", "error")
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_activity('LOGOUT', details='Logged out')
    logout_user()
    flash(t('msg_logout_success') if t('msg_logout_success') != 'msg_logout_success' else "🚪 Đã đăng xuất.", "success")
    return redirect(url_for('auth.login'))

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')
        if not current_pw or not new_pw or not confirm_pw:
            flash(t('err_fill_all_fields'), "warning")
            return redirect(url_for('auth.change_password'))
        if new_pw != confirm_pw:
            flash(t('err_password_mismatch'), "warning")
            return redirect(url_for('auth.change_password'))
        user = current_user
        if not user.check_password(current_pw):
            flash(t('err_current_password_incorrect'), "danger")
            return redirect(url_for('auth.change_password'))
        user.set_password(new_pw)
        db.session.commit()
        flash(t('msg_password_change_success'), "success")
        return redirect(url_for('main.dashboard'))
    return render_template('change_password.html')
