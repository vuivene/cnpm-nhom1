from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection
from datetime import date
import re

benh_nhan_bp = Blueprint('benh_nhan', __name__)

# =========================================================
# 1. TRANG DANH SÁCH BỆNH NHÂN + TÌM KIẾM + BỘ LỌC
# =========================================================
@benh_nhan_bp.route('/benh-nhan', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    search_query = request.args.get('search', '').strip()
    trang_thai_filter = request.args.get('trang_thai', 'Tất cả')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT bn.*, ba.MaBenhAn, ba.ChanDoan, ba.TrangThai
        FROM BenhNhan bn
        LEFT JOIN BenhAn ba ON ba.MaBenhAn = (
            SELECT ba2.MaBenhAn 
            FROM BenhAn ba2 
            WHERE ba2.MaBenhNhan = bn.MaBenhNhan 
            ORDER BY ba2.NgayKham DESC 
            LIMIT 1
        )
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (bn.MaBenhNhan LIKE %s OR bn.HoTen LIKE %s OR bn.SoDienThoai LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if trang_thai_filter != 'Tất cả':
        if trang_thai_filter == 'Đang điều trị':
            sql += " AND ba.TrangThai = 'Đang điều trị'"
        elif trang_thai_filter == 'Đã hoàn thành':
            sql += " AND ba.TrangThai = 'Đã hoàn thành'"

    cursor.execute(sql, tuple(params))
    ds_benh_nhan = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'pages/benh-nhan/benh-nhan.html', 
        benh_nhan=ds_benh_nhan, 
        search_query=search_query,
        current_trang_thai=trang_thai_filter
    )

# =========================================================
# 2. ĐIỀU HƯỚNG FORM (DÙNG CHUNG CHO XEM, THÊM VÀ SỬA)
# =========================================================
@benh_nhan_bp.route('/benh-nhan/form', methods=['GET'])
def form_benh_nhan():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.args.get('action', 'add')
    ma_bn = request.args.get('id', '')
    
    data = None
    if action in ['view', 'edit'] and ma_bn:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT bn.*, ba.MaBenhAn, ba.MaNhanVien, ba.ChanDoan, ba.KeHoachDieuTri, ba.TrangThai AS TrangThaiBA, ba.GhiChu
            FROM BenhNhan bn
            LEFT JOIN BenhAn ba ON ba.MaBenhAn = (
                SELECT ba2.MaBenhAn FROM BenhAn ba2 WHERE ba2.MaBenhNhan = bn.MaBenhNhan ORDER BY ba2.NgayKham DESC LIMIT 1
            )
            WHERE bn.MaBenhNhan = %s
        """, (ma_bn,))
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        
    return render_template('pages/benh-nhan/them-benh-nhan.html', action=action, data=data)

# =========================================================
# 3. XỬ LÝ LƯU DỮ LIỆU (TÍCH HỢP VALIDATION SERVER-SIDE)
# =========================================================
@benh_nhan_bp.route('/benh-nhan/save', methods=['POST'])
def save_benh_nhan():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.form.get('action')
    
    ho_ten = request.form.get('ho_ten', '').strip()
    gioi_tinh = request.form.get('gioi_tinh')
    ngay_sinh = request.form.get('ngay_sinh')
    sdt = request.form.get('sdt', '').strip()
    email = request.form.get('email', '').strip()
    dia_chi = request.form.get('dia_chi', '').strip()
    tien_su_di_ung = request.form.get('tien_su_di_ung', '').strip()
    
    ma_nv_bac_si = request.form.get('ma_nv_bac_si', '').strip()
    chan_doan = request.form.get('chan_doan', '').strip()
    ke_hoach = request.form.get('ke_hoach', '').strip()
    trang_thai_ba = request.form.get('trang_thai_ba')
    ghi_chu = request.form.get('ghi_chu', '').strip()

    # --- TẦNG VALIDATION PHÍA SERVER ---
    if not all([ho_ten, ngay_sinh, gioi_tinh, sdt, ma_nv_bac_si, chan_doan]):
        flash('Lỗi! Vui lòng điền đầy đủ các thông tin bắt buộc!')
        return redirect(request.referrer)

    if not (10 <= len(ho_ten) <= 35):
        flash('Lỗi! Họ tên phải từ 10 đến 35 ký tự.')
        return redirect(request.referrer)

    if gioi_tinh == 'Chọn giới tính':
        flash('Lỗi! Vui lòng chọn giới tính hợp lệ.')
        return redirect(request.referrer)

    # Kiểm tra tuổi tác (3 - 90 tuổi)
    nam_sinh = int(ngay_sinh.split('-')[0])
    tuoi = date.today().year - nam_sinh
    if not (3 <= tuoi <= 90):
        flash('Lỗi! Tuổi bệnh nhân phải nằm trong độ tuổi từ 3 đến 90.')
        return redirect(request.referrer)

    # Kiểm tra số điện thoại (10 số, bắt đầu bằng số 0)
    if not re.match(r"^0\d{9}$", sdt):
        flash('Lỗi! Số điện thoại phải gồm 10 chữ số và bắt đầu bằng số 0.')
        return redirect(request.referrer)

    # Kiểm tra cấu trúc Email và độ dài chuỗi cục bộ đứng trước dấu @
    if email:
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            flash('Lỗi! Email không đúng cấu trúc quy định.')
            return redirect(request.referrer)
        if len(email.split('@')[0]) < 6:
            flash('Lỗi! Email phải có tối thiểu 6 ký tự nằm trước ký tự @.')
            return redirect(request.referrer)

    if dia_chi and not (10 <= len(dia_chi) <= 60):
        flash('Lỗi! Địa chỉ nhập vào phải từ 10 đến 60 ký tự.')
        return redirect(request.referrer)

    # Ép range 10-80 ký tự cho các ô dữ liệu văn bản mô tả bệnh án
    if tien_su_di_ung and not (5 <= len(tien_su_di_ung) <= 80):
        flash('Lỗi! Tiền sử / Dị ứng phải từ 5 đến 80 ký tự.')
        return redirect(request.referrer)
    if not (5 <= len(chan_doan) <= 80):
        flash('Lỗi! Chẩn đoán phải từ 5 đến 80 ký tự.')
        return redirect(request.referrer)
    if ke_hoach and not (5 <= len(ke_hoach) <= 80):
        flash('Lỗi! Kế hoạch điều trị phải từ 5 đến 80 ký tự.')
        return redirect(request.referrer)
    if ghi_chu and not (0 <= len(ghi_chu) <= 80):
        flash('Lỗi! Ghi chú phải từ 0 đến 80 ký tự.')
        return redirect(request.referrer)

    # Kiểm tra cấu trúc mã NV bác sĩ
    if not re.match(r"^NV\d+$", ma_nv_bac_si):
        flash('Lỗi! Mã bác sĩ điều trị phải có dạng cấu trúc là NV<số>.')
        return redirect(request.referrer)

    # Ràng buộc trạng thái Đang điều trị
    if trang_thai_ba == 'Đang điều trị':
        if not all([email, dia_chi, tien_su_di_ung, ke_hoach, ghi_chu]):
            flash('Lỗi! Trạng thái Đang điều trị bắt buộc phải nhập tất cả thông tin bổ sung.')
            return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # KIỂM TRA MÃ NV CÓ PHẢI BÁC SĨ KHÔNG TRONG CSDL
        cursor.execute("SELECT ChucVu FROM TaiKhoan WHERE MaNhanVien = %s", (ma_nv_bac_si,))
        tk_check = cursor.fetchone()
        
        if not tk_check or tk_check['ChucVu'] != 'Bác sĩ':
            flash(f'Lỗi! Nhân viên có mã {ma_nv_bac_si} không tồn tại hoặc không giữ chức vụ Bác sĩ!')
            return redirect(request.referrer)

        # Chuyển đổi con trỏ về dạng Tuple phục vụ câu lệnh Insert/Update bên dưới
        cursor.close()
        cursor = conn.cursor()

        if action == 'add':
            cursor.execute("SELECT MaBenhNhan FROM BenhNhan ORDER BY MaBenhNhan DESC LIMIT 1")
            last_bn = cursor.fetchone()
            new_ma_bn = f"BN{int(last_bn[0][2:]) + 1:02d}" if last_bn else "BN01"

            cursor.execute("SELECT MaBenhAn FROM BenhAn ORDER BY MaBenhAn DESC LIMIT 1")
            last_ba = cursor.fetchone()
            new_ma_ba = f"BA{int(last_ba[0][2:]) + 1:02d}" if last_ba else "BA01"

            # 1. Ghi dữ liệu vào bảng BenhNhan
            cursor.execute("""
                INSERT INTO BenhNhan (MaBenhNhan, HoTen, GioiTinh, NgaySinh, SoDienThoai, Email, DiaChi, TienSuYKhoa, DiUng)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (new_ma_bn, ho_ten, gioi_tinh, ngay_sinh, sdt, email if email else None, dia_chi if dia_chi else None, tien_su_di_ung if tien_su_di_ung else None, tien_su_di_ung if tien_su_di_ung else None))

            # 2. Ghi dữ liệu vào bảng BenhAn
            cursor.execute("""
                INSERT INTO BenhAn (MaBenhAn, MaBenhNhan, MaNhanVien, NgayKham, ChanDoan, KeHoachDieuTri, TrangThai, GhiChu)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)
            """, (new_ma_ba, new_ma_bn, ma_nv_bac_si, chan_doan, ke_hoach if ke_hoach else None, trang_thai_ba, ghi_chu if ghi_chu else None))
            
            flash(f'Thêm mới hồ sơ bệnh nhân {new_ma_bn} và bệnh án {new_ma_ba} thành công!')

        elif action == 'edit':
            ma_bn = request.form.get('ma_bn')
            ma_ba = request.form.get('ma_ba')
            
            cursor.execute("""
                UPDATE BenhNhan 
                SET HoTen=%s, GioiTinh=%s, NgaySinh=%s, SoDienThoai=%s, Email=%s, DiaChi=%s, TienSuYKhoa=%s, DiUng=%s
                WHERE MaBenhNhan=%s
            """, (ho_ten, gioi_tinh, ngay_sinh, sdt, email if email else None, dia_chi if dia_chi else None, tien_su_di_ung if tien_su_di_ung else None, tien_su_di_ung if tien_su_di_ung else None, ma_bn))

            if ma_ba:
                cursor.execute("""
                    UPDATE BenhAn 
                    SET MaNhanVien=%s, ChanDoan=%s, KeHoachDieuTri=%s, TrangThai=%s, GhiChu=%s
                    WHERE MaBenhAn=%s
                """, (ma_nv_bac_si, chan_doan, ke_hoach if ke_hoach else None, trang_thai_ba, ghi_chu if ghi_chu else None, ma_ba))
            else:
                cursor.execute("SELECT MaBenhAn FROM BenhAn ORDER BY MaBenhAn DESC LIMIT 1")
                last_ba = cursor.fetchone()
                new_ma_ba = f"BA{int(last_ba[0][2:]) + 1:02d}" if last_ba else "BA01"
                
                cursor.execute("""
                    INSERT INTO BenhAn (MaBenhAn, MaBenhNhan, MaNhanVien, NgayKham, ChanDoan, KeHoachDieuTri, TrangThai, GhiChu)
                    VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)
                """, (new_ma_ba, ma_bn, ma_nv_bac_si, chan_doan, ke_hoach if ke_hoach else None, trang_thai_ba, ghi_chu if ghi_chu else None))

            flash(f'Cập nhật hồ sơ bệnh nhân {ma_bn} thành công!')

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi hệ thống database: {e}')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('benh_nhan.danh_sach'))

# =========================================================
# 4. TÁC VỤ XÓA BỆNH NHÂN
# =========================================================
@benh_nhan_bp.route('/benh-nhan/xoa/<string:id>', methods=['GET'])
def xoa_benh_nhan(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM BenhAn WHERE MaBenhNhan = %s", (id,))
        cursor.execute("DELETE FROM HoaDon WHERE MaBenhNhan = %s", (id,))
        cursor.execute("DELETE FROM LichHen WHERE MaBenhNhan = %s", (id,))
        cursor.execute("DELETE FROM BenhNhan WHERE MaBenhNhan = %s", (id,))
        conn.commit()
        flash(f'Đã xóa sạch hồ sơ bệnh nhân {id} khỏi hệ thống.')
    except Exception as e:
        conn.rollback()
        flash(f'Không thể xóa do bệnh nhân đã có chi tiết hóa đơn/đơn thuốc: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('benh_nhan.danh_sach'))