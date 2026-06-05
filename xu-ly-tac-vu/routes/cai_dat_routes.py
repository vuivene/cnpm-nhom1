from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

cai_dat_bp = Blueprint('cai_dat', __name__)

@cai_dat_bp.route('/cai-dat', methods=['GET'])
def index():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Lấy thông số Cài Đặt Phòng Khám
    cursor.execute("SELECT MaCaiDat, GiaTri FROM CaiDat")
    settings = cursor.fetchall()
    config = {item['MaCaiDat']: item['GiaTri'] for item in settings}

    # 2. Lấy thông tin Tài Khoản của user đang đăng nhập
    ma_nv = session.get('id')
    cursor.execute("""
        SELECT nv.Email, tk.TenDangNhap 
        FROM NhanVien nv 
        JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien 
        WHERE nv.MaNhanVien = %s
    """, (ma_nv,))
    user_info = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('pages/cai-dat.html', config=config, user=user_info)

@cai_dat_bp.route('/cai-dat/save-clinic', methods=['POST'])
def save_clinic():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    data = {
        'CLINIC_NAME': ('Tên Phòng Khám', request.form.get('clinic_name')),
        'CLINIC_ADDRESS': ('Địa chỉ phòng khám', request.form.get('clinic_address')),
        'HOTLINE': ('Hotline', request.form.get('hotline')),
        'OPEN_TIME': ('Giờ mở cửa', request.form.get('open_time')),
        'CLOSE_TIME': ('Giờ đóng cửa', request.form.get('close_time')),
        'TAX_RATE': ('Thuế VAT', request.form.get('tax_rate'))
    }

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for ma_cd, (ten_cd, gia_tri) in data.items():
            if gia_tri is not None:
                cursor.execute("""
                    INSERT INTO CaiDat (MaCaiDat, TenCaiDat, GiaTri, MoTa) 
                    VALUES (%s, %s, %s, '')
                    ON DUPLICATE KEY UPDATE GiaTri = VALUES(GiaTri), TenCaiDat = VALUES(TenCaiDat)
                """, (ma_cd, ten_cd, gia_tri))

        upload_folder = 'static/img'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        favicon = request.files.get('favicon')
        logo = request.files.get('logo')

        if favicon and favicon.filename:
            fav_name = secure_filename(favicon.filename)
            favicon.save(os.path.join(upload_folder, fav_name))
            cursor.execute("INSERT INTO CaiDat (MaCaiDat, TenCaiDat, GiaTri) VALUES ('FAVICON', 'Favicon Tab', %s) ON DUPLICATE KEY UPDATE GiaTri = VALUES(GiaTri)", (fav_name,))

        if logo and logo.filename:
            logo_name = secure_filename(logo.filename)
            logo.save(os.path.join(upload_folder, logo_name))
            cursor.execute("INSERT INTO CaiDat (MaCaiDat, TenCaiDat, GiaTri) VALUES ('LOGO', 'Logo Sidebar', %s) ON DUPLICATE KEY UPDATE GiaTri = VALUES(GiaTri)", (logo_name,))

        conn.commit()
        flash('Đã lưu cấu hình phòng khám thành công!')
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi khi lưu cấu hình: {e}')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('cai_dat.index'))

# =========================================================
# XỬ LÝ LƯU TÀI KHOẢN + TỰ ĐỘNG ĐĂNG XUẤT SAU KHI ĐỔI THÀNH CÔNG
# =========================================================
@cai_dat_bp.route('/cai-dat/save-account', methods=['POST'])
def save_account():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    email = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    ma_nv = session.get('id')

    email_val = email if email != "" else None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Cập nhật bảng NhanVien
        cursor.execute("UPDATE NhanVien SET Email = %s WHERE MaNhanVien = %s", (email_val, ma_nv))
        
        # 2. Cập nhật bảng TaiKhoan
        if password: 
            hashed_password = generate_password_hash(password)
            cursor.execute("UPDATE TaiKhoan SET TenDangNhap = %s, MatKhau = %s WHERE MaNhanVien = %s", (username, hashed_password, ma_nv))
        else: 
            cursor.execute("UPDATE TaiKhoan SET TenDangNhap = %s WHERE MaNhanVien = %s", (username, ma_nv))
            
        conn.commit()
        
        # 3. Tiến hành xóa Session để ép buộc đăng xuất đồng bộ hệ thống bảo mật
        session.clear()
        flash('Thay đổi thông tin tài khoản thành công! Vui lòng đăng nhập lại với thông tin mới.')
        
        # Chuyển hướng thẳng về trang đăng nhập của hệ thống thay vì ở lại trang cài đặt
        return redirect(url_for('login'))
        
    except Exception as e:
        conn.rollback()
        flash('Lỗi! Tên đăng nhập này có thể đã được sử dụng bởi người khác.')
        return redirect(url_for('cai_dat.index'))
    finally:
        cursor.close()
        conn.close()