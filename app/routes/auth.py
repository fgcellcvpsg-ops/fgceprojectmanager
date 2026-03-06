from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
import time
import os
from ..models import User
from ..extensions import db, limiter
from app.utils import t, log_activity

import logging
import sys

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
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
                        flash("❌ Tài khoản chưa được phép đăng nhập.", "error")
                        return redirect(url_for('auth.login'))
                    login_user(user)
                    # log_activity('LOGIN', details='Logged in successfully')
                    flash("✅ Đăng nhập thành công!", "success")
                    return redirect(url_for('main.dashboard'))
            
            flash("❌ Sai tài khoản hoặc mật khẩu.", "error")
        except Exception as e:
            current_app.logger.exception("Login error: %s", e)
            flash("❌ Lỗi đăng nhập. Vui lòng thử lại.", "error")
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_activity('LOGOUT', details='Logged out')
    logout_user()
    flash("🚪 Đã đăng xuất.", "success")
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
