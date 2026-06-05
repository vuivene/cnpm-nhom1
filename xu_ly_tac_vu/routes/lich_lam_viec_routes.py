from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection
from datetime import datetime

lich_lam_viec_bp = Blueprint('lich_lam_viec', __name__)

def format_time_hh_mm(t):
    if not t: return ""
    parts = str(t).split(':')
    if len(parts) >= 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    return str(t)

def check_is_past(ngay, gio):
    try:
        dt_str = f"{ngay} {gio}"
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M") < datetime.now()
    except:
        return False

@lich_lam_viec_bp.route('/lich-lam-viec', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    search_query = request.args.get('search', '').strip()
    ngay_lam = request.args.get('ngay_lam', '')
    ca_lam = request.args.get('ca_lam', 'Tất cả ca')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT l.*, nv.HoTen, tk.ChucVu, p.TenPhong 
        FROM LichLamViec l
        JOIN NhanVien nv ON l.MaNhanVien = nv.MaNhanVien
        LEFT JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien
        LEFT JOIN Phong p ON l.MaPhong = p.MaPhong
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (nv.HoTen LIKE %s OR p.TenPhong LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if ngay_lam:
        sql += " AND l.NgayLamViec = %s"
        params.append(ngay_lam)
    if ca_lam == 'Ca Sáng':
        sql += " AND l.ThoiGianBatDau < '12:00:00'"
    elif ca_lam == 'Ca Chiều':
        sql += " AND l.ThoiGianBatDau >= '12:00:00'"
        
    sql += " ORDER BY l.NgayLamViec DESC, l.ThoiGianBatDau ASC"
    cursor.execute(sql, tuple(params))
    ds_lich = cursor.fetchall()
    
    for l in ds_lich:
        gio_bd = format_time_hh_mm(l['ThoiGianBatDau'])
        l['ThoiGianBatDau'] = gio_bd
        l['ThoiGianKetThuc'] = format_time_hh_mm(l['ThoiGianKetThuc'])
        l['is_past'] = check_is_past(l['NgayLamViec'], gio_bd)
        
    cursor.close()
    conn.close()
    
    return render_template('pages/lich-lam-viec/lich-lam-viec.html', 
                           lich_lam_viec=ds_lich, search_query=search_query, 
                           current_ngay=ngay_lam, current_ca=ca_lam)

@lich_lam_viec_bp.route('/lich-lam-viec/form', methods=['GET'])
def form():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    action = request.args.get('action', 'add')
    ma_lich = request.args.get('id')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT nv.MaNhanVien, nv.HoTen, tk.ChucVu FROM NhanVien nv LEFT JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien")
    ds_nhan_vien = cursor.fetchall()
    cursor.execute("SELECT * FROM Phong")
    ds_phong = cursor.fetchall()
    
    lich_data = {}
    is_past = False
    
    if action in ['view', 'edit'] and ma_lich:
        cursor.execute("SELECT * FROM LichLamViec WHERE MaLich = %s", (ma_lich,))
        lich_data = cursor.fetchone()
        
        if lich_data:
            gio_bd = format_time_hh_mm(lich_data.get('ThoiGianBatDau'))
            lich_data['ThoiGianBatDau'] = gio_bd
            lich_data['ThoiGianKetThuc'] = format_time_hh_mm(lich_data.get('ThoiGianKetThuc'))
            is_past = check_is_past(lich_data['NgayLamViec'], gio_bd)
            
            if is_past and action == 'edit':
                flash('Lịch làm việc này đã qua, hệ thống chỉ cho phép xem hoặc xóa!')
                action = 'view'
                
    cursor.close()
    conn.close()
    
    return render_template('pages/lich-lam-viec/them-lich-lam-viec.html', 
                           action=action, data=lich_data, 
                           nhan_vien=ds_nhan_vien, phong=ds_phong, is_past=is_past)

@lich_lam_viec_bp.route('/lich-lam-viec/save', methods=['POST'])
def save():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    action = request.form.get('action')
    ma_lich = request.form.get('ma_lich')
    ma_nv = request.form.get('ma_nv')
    ma_phong = request.form.get('ma_phong')
    ngay_lam = request.form.get('ngay_lam')
    gio_bat_dau = request.form.get('gio_bat_dau')
    gio_ket_thuc = request.form.get('gio_ket_thuc')
    
    if not ma_phong or ma_phong.strip() == "": 
        ma_phong = None
    
    if not all([ma_nv, ngay_lam, gio_bat_dau, gio_ket_thuc]):
        flash('Lỗi: Vui lòng điền đầy đủ các thông tin bắt buộc!')
        return redirect(request.referrer)

    if check_is_past(ngay_lam, gio_bat_dau):
        flash('Lỗi: Ngày giờ bắt đầu phân ca đã ở trong quá khứ!')
        return redirect(request.referrer)
        
    h_bd = int(gio_bat_dau.split(':')[0])
    h_kt = int(gio_ket_thuc.split(':')[0])
    if (h_bd >= 22 or h_bd < 5) or (h_kt >= 22 or h_kt < 5):
        flash('Lỗi: Ca làm việc không được nằm trong khung giờ từ 22h đến 5h sáng!')
        return redirect(request.referrer)

    if gio_ket_thuc <= gio_bat_dau:
        flash('Lỗi: Giờ kết thúc ca làm phải lớn hơn giờ bắt đầu!')
        return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # --- LẤY CHỨC VỤ CỦA NHÂN VIÊN ĐỂ ĐÁNH GIÁ CHUYÊN MÔN ---
        cursor.execute("SELECT ChucVu FROM TaiKhoan WHERE MaNhanVien = %s", (ma_nv,))
        nv_info = cursor.fetchone()
        chuc_vu = nv_info['ChucVu'] if nv_info else ''

        # 1. RÀNG BUỘC: Lễ tân không làm việc trong các khu vực phòng khám
        if chuc_vu == 'Lễ tân' and ma_phong is not None:
            flash('Lỗi: Lễ tân không được làm việc trong các khu vực phòng khám!')
            return redirect(request.referrer)

        # Cấu trúc loại trừ ID khi cập nhật ở chế độ 'edit' tránh tự bắt trùng chính mình
        extra_sql = " AND MaLich != %s" if action == 'edit' else ""
        extra_params = (int(ma_lich),) if action == 'edit' else ()

        # 2. RÀNG BUỘC: 1 nhân viên 1 ngày chỉ làm việc tối đa 1 ca
        sql_one_shift = f"SELECT COUNT(*) AS cnt FROM LichLamViec WHERE MaNhanVien = %s AND NgayLamViec = %s {extra_sql}"
        cursor.execute(sql_one_shift, (ma_nv, ngay_lam) + extra_params)
        if cursor.fetchone()['cnt'] > 0:
            flash('Lỗi: Nhân viên này đã được phân bổ ca làm việc khác trong ngày hôm nay!')
            return redirect(request.referrer)

        # 3. RÀNG BUỘC: Trong 1 khung thời gian giống nhau 1 nhân viên không thể ở hai phòng cùng lúc (Trùng/Giao nhau)
        sql_overlap_nv = f"""
            SELECT COUNT(*) AS cnt FROM LichLamViec 
            WHERE MaNhanVien = %s AND NgayLamViec = %s 
              AND ((ThoiGianBatDau <= %s AND ThoiGianKetThuc > %s)
               OR  (ThoiGianBatDau < %s AND ThoiGianKetThuc >= %s)
               OR  (%s <= ThoiGianBatDau AND %s > ThoiGianBatDau))
              {extra_sql}
        """
        cursor.execute(sql_overlap_nv, (ma_nv, ngay_lam, gio_bat_dau, gio_bat_dau, gio_ket_thuc, gio_ket_thuc, gio_bat_dau, gio_ket_thuc) + extra_params)
        if cursor.fetchone()['cnt'] > 0:
            flash('Lỗi: Khung giờ làm việc của nhân viên bị trùng lặp hoặc giao nhau với ca trực khác!')
            return redirect(request.referrer)

        # 4. RÀNG BUỘC PHÒNG KHÁM: Tối đa 2 nhân viên cùng làm việc và bắt buộc phải là 2 bác sĩ
        if ma_phong is not None:
            # Nếu nhân viên được xếp không phải bác sĩ thì từ chối luôn
            if chuc_vu != 'Bác sĩ':
                flash('Lỗi: Chỉ có nhân sự giữ chức vụ Bác sĩ mới được quyền phân ca vào phòng khám!')
                return redirect(request.referrer)

            # Đếm số lượng bác sĩ đang trùng khung thời gian tại phòng này
            sql_overlap_room = f"""
                SELECT COUNT(*) AS cnt FROM LichLamViec l
                JOIN TaiKhoan tk ON l.MaNhanVien = tk.MaNhanVien
                WHERE l.MaPhong = %s AND l.NgayLamViec = %s 
                  AND tk.ChucVu = 'Bác sĩ'
                  AND ((l.ThoiGianBatDau <= %s AND l.ThoiGianKetThuc > %s)
                   OR  (l.ThoiGianBatDau < %s AND l.ThoiGianKetThuc >= %s)
                   OR  (%s <= l.ThoiGianBatDau AND %s > l.ThoiGianBatDau))
                  {extra_sql}
            """
            cursor.execute(sql_overlap_room, (ma_phong, ngay_lam, gio_bat_dau, gio_bat_dau, gio_ket_thuc, gio_ket_thuc, gio_bat_dau, gio_ket_thuc) + extra_params)
            if cursor.fetchone()['cnt'] >= 2:
                flash('Lỗi: Phòng khám này đã đạt giới hạn tối đa 2 Bác sĩ làm việc chung trong khung giờ này!')
                return redirect(request.referrer)

        # --- TIẾN HÀNH LƯU DỮ LIỆU KHI VƯỢT QUA TẤT CẢ RÀNG BUỘC ---
        cursor.close()
        cursor = conn.cursor()

        if action == 'add':
            cursor.execute("""
                INSERT INTO LichLamViec (MaNhanVien, MaPhong, NgayLamViec, ThoiGianBatDau, ThoiGianKetThuc) 
                VALUES (%s, %s, %s, %s, %s)
            """, (ma_nv, ma_phong, ngay_lam, gio_bat_dau, gio_ket_thuc))
            flash('Thêm lịch làm việc mới thành công!')
        elif action == 'edit':
            cursor.execute("""
                UPDATE LichLamViec 
                SET MaNhanVien=%s, MaPhong=%s, NgayLamViec=%s, ThoiGianBatDau=%s, ThoiGianKetThuc=%s 
                WHERE MaLich=%s
            """, (ma_nv, ma_phong, ngay_lam, gio_bat_dau, gio_ket_thuc, ma_lich))
            flash('Cập nhật lịch làm việc thành công!')
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi hệ thống database: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('lich_lam_viec.danh_sach'))

@lich_lam_viec_bp.route('/lich-lam-viec/delete/<int:id>', methods=['GET'])
def delete(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM LichLamViec WHERE MaLich = %s", (id,))
        conn.commit()
        flash('Đã xóa ca làm việc thành công!')
    except:
        conn.rollback()
        flash('Lỗi khi xóa dữ liệu trực thuộc.')
    finally:
        cursor.close()
        conn.close()
    return redirect(request.referrer)