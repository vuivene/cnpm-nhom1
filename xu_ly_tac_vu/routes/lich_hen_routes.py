from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db_config import get_db_connection
from datetime import datetime, timedelta

lich_hen_bp = Blueprint('lich_hen', __name__)

# --- API: TÌM BÁC SĨ RẢNH THEO THỜI GIAN ---
@lich_hen_bp.route('/api/bac-si-ranh', methods=['GET'])
def get_bac_si_ranh():
    time_str = request.args.get('time')
    if not time_str: return jsonify([])
    
    try:
        dt = datetime.strptime(time_str, '%Y-%m-%dT%H:%M')
        ngay = dt.date()
        gio = dt.time()
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Chỉ lấy nhân viên có chức vụ Bác sĩ và ĐANG CÓ CA LÀM BAO PHỦ GIỜ HẸN
        cursor.execute("""
            SELECT nv.MaNhanVien, nv.HoTen 
            FROM LichLamViec llv
            JOIN NhanVien nv ON llv.MaNhanVien = nv.MaNhanVien
            JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien
            WHERE llv.NgayLamViec = %s 
              AND llv.ThoiGianBatDau <= %s 
              AND llv.ThoiGianKetThuc >= %s
              AND tk.ChucVu LIKE '%Bác sĩ%'
        """, (ngay, gio, gio))
        
        bac_si = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(bac_si)
    except:
        return jsonify([])

# --- DANH SÁCH LỊCH HẸN (GẮN CỜ HIGHLIGHT NẾU CA LÀM CỦA BÁC SĨ BỊ HỦY/THAY ĐỔI) ---
@lich_hen_bp.route('/lich-hen', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    search_query = request.args.get('search', '').strip()
    ngay_hen = request.args.get('ngay_hen', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT lh.*, bn.HoTen AS TenBenhNhan, bn.SoDienThoai, nv.HoTen AS TenBacSi
        FROM LichHen lh
        LEFT JOIN BenhNhan bn ON lh.MaBenhNhan = bn.MaBenhNhan
        LEFT JOIN NhanVien nv ON lh.MaNhanVien = nv.MaNhanVien
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (bn.HoTen LIKE %s OR bn.SoDienThoai LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if ngay_hen:
        sql += " AND DATE(lh.ThoiGianHen) = %s"
        params.append(ngay_hen)
        
    sql += " ORDER BY lh.ThoiGianHen DESC"
    cursor.execute(sql, tuple(params))
    ds_lich_hen = cursor.fetchall()
    
    # KIỂM TRA HIỂN THỊ HIGHLIGHT: Nếu bác sĩ không có lịch làm việc bao phủ lịch hẹn (bị hủy ca)
    for lh in ds_lich_hen:
        lh['highlight_can_doi'] = False
        if lh['MaNhanVien'] and lh['ThoiGianHen'] and lh['TrangThai'] == 'Chờ xác nhận':
            ngay = lh['ThoiGianHen'].date()
            gio = lh['ThoiGianHen'].time()
            
            cursor.execute("""
                SELECT COUNT(*) AS cnt FROM LichLamViec 
                WHERE MaNhanVien = %s AND NgayLamViec = %s 
                  AND ThoiGianBatDau <= %s AND ThoiGianKetThuc >= %s
            """, (lh['MaNhanVien'], ngay, gio, gio))
            
            if cursor.fetchone()['cnt'] == 0:
                lh['highlight_can_doi'] = True # Đánh dấu để Frontend nhuộm đỏ/cảnh báo đổi lịch

    cursor.close()
    conn.close()
    
    return render_template('pages/lich-hen/lich-hen.html', 
                           lich_hen=ds_lich_hen, search_query=search_query, current_ngay=ngay_hen)

# --- FORM THÊM / SỬA / XEM ---
@lich_hen_bp.route('/lich-hen/form', methods=['GET'])
def form():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    action = request.args.get('action', 'add')
    ma_lh = request.args.get('id')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    data = {}
    if action in ['view', 'edit'] and ma_lh:
        cursor.execute("""
            SELECT lh.*, bn.HoTen AS TenBenhNhan, bn.SoDienThoai, nv.HoTen AS TenBacSi 
            FROM LichHen lh 
            LEFT JOIN BenhNhan bn ON lh.MaBenhNhan = bn.MaBenhNhan
            LEFT JOIN NhanVien nv ON lh.MaNhanVien = nv.MaNhanVien
            WHERE lh.MaLichHen = %s
        """, (ma_lh,))
        data = cursor.fetchone()
        if data and data['ThoiGianHen']:
            data['ThoiGianHenStr'] = data['ThoiGianHen'].strftime('%Y-%m-%dT%H:%M')
            
    cursor.close()
    conn.close()
    
    return render_template('pages/lich-hen/them-lich-hen.html', action=action, data=data)

# --- XỬ LÝ LƯU THÔNG TIN + RÀNG BUỘC NGHIỆP VỤ ---
@lich_hen_bp.route('/lich-hen/save', methods=['POST'])
def save():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    action = request.form.get('action')
    ma_lh = request.form.get('ma_lich_hen')
    ten_bn = request.form.get('ten_benh_nhan', '').strip()
    sdt = request.form.get('so_dien_thoai', '').strip()
    thoi_gian_hen = request.form.get('thoi_gian_hen')
    ma_nv = request.form.get('ma_nv')
    ly_do = request.form.get('ly_do_kham', '').strip()
    trang_thai = request.form.get('trang_thai', 'Chờ xác nhận')
    
    try:
        dt_hen = datetime.strptime(thoi_gian_hen, '%Y-%m-%dT%H:%M')
        if dt_hen < datetime.now():
            flash('Lỗi: Thời gian hẹn phải ở trong tương lai!')
            return redirect(request.referrer)
    except:
        flash('Lỗi: Định dạng thời gian không hợp lệ!')
        return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("START TRANSACTION")
        
        # Lấy hoặc tạo thông tin MaBenhNhan trước để phục vụ việc kiểm tra trùng chéo ca
        cursor.execute("SELECT MaBenhNhan FROM BenhNhan WHERE SoDienThoai = %s LIMIT 1 FOR UPDATE", (sdt,))
        bn_exist = cursor.fetchone()
        if bn_exist:
            ma_bn = bn_exist['MaBenhNhan']
        else:
            cursor.execute("SELECT MaBenhNhan FROM BenhNhan ORDER BY MaBenhNhan DESC LIMIT 1 FOR UPDATE")
            last_bn = cursor.fetchone()
            num_bn = int(last_bn['MaBenhNhan'][2:]) + 1 if last_bn and last_bn['MaBenhNhan'] else 1
            ma_bn = f"BN{num_bn:02d}"
            cursor.execute("INSERT INTO BenhNhan (MaBenhNhan, HoTen, SoDienThoai) VALUES (%s, %s, %s)", (ma_bn, ten_bn, sdt))

        # --- KIỂM TRA 1: KHÔNG THỂ ĐẶT LỊCH NGOÀI GIỜ HOẠT ĐỘNG (CA LÀM) CỦA BÁC SĨ ---
        ngay_date = dt_hen.date()
        gio_time = dt_hen.time()
        cursor.execute("""
            SELECT ThoiGianBatDau, ThoiGianKetThuc FROM LichLamViec 
            WHERE MaNhanVien = %s AND NgayLamViec = %s 
              AND ThoiGianBatDau <= %s AND ThoiGianKetThuc >= %s
            LIMIT 1
        """, (ma_nv, ngay_date, gio_time, gio_time))
        ca_truc = cursor.fetchone()
        
        if not ca_truc:
            flash('Lỗi: Không thể đặt lịch hẹn ngoài giờ hoạt động hoặc ngoài ca trực của bác sĩ!')
            cursor.execute("ROLLBACK")
            return redirect(request.referrer)
            
        t_bat_dau = ca_truc['ThoiGianBatDau']
        t_ket_thuc = ca_truc['ThoiGianKetThuc']

        # Biến loại trừ khi Sửa
        extra_sql = " AND MaLichHen != %s" if action == 'edit' else ""
        extra_params = (int(ma_lh),) if action == 'edit' else ()

        # --- KIỂM TRA 2: MỘT BÁC SĨ KHÔNG QUÁ 4 LỊCH HẸN TRONG 1 CA LÀM VIỆC ---
        cursor.execute(f"""
            SELECT COUNT(*) AS cnt FROM LichHen 
            WHERE MaNhanVien = %s 
              AND DATE(ThoiGianHen) = %s 
              AND TIME(ThoiGianHen) >= %s 
              AND TIME(ThoiGianHen) <= %s
              AND TrangThai != 'Đã hủy'
              {extra_sql}
        """, (ma_nv, ngay_date, t_bat_dau, t_ket_thuc) + extra_params)
        
        if cursor.fetchone()['cnt'] >= 4:
            flash('Lỗi: Bác sĩ phụ trách đã đạt giới hạn tối đa (4 lịch hẹn) trong ca làm việc này!')
            cursor.execute("ROLLBACK")
            return redirect(request.referrer)

        # --- KIỂM TRA 3: CÁC LỊCH HẸN CỦA BÁC SĨ KHÔNG ĐƯỢC SÁT NHAU QUÁ 1 GIỜ (60 PHÚT) ---
        cursor.execute(f"""
            SELECT ThoiGianHen FROM LichHen 
            WHERE MaNhanVien = %s 
              AND DATE(ThoiGianHen) = %s
              AND TrangThai != 'Đã hủy'
              {extra_sql}
        """, (ma_nv, ngay_date) + extra_params)
        cac_lich_hen_cu = cursor.fetchall()
        
        for lh_cu in cac_lich_hen_cu:
            diff = abs((dt_hen - lh_cu['ThoiGianHen']).total_seconds())
            if diff < 3600: # 3600 giây = 1 giờ
                flash('Lỗi: Khoảng cách giữa các lịch hẹn của bác sĩ phải cách nhau tối thiểu 1 giờ!')
                cursor.execute("ROLLBACK")
                return redirect(request.referrer)

        # --- KIỂM TRA 4: BỆNH NHÂN KHÔNG THỂ HẸN NHIỀU BÁC SĨ TRONG CÙNG CA LÀM ---
        cursor.execute(f"""
            SELECT lh.ThoiGianHen, lh.MaNhanVien FROM LichHen lh
            WHERE lh.MaBenhNhan = %s 
              AND DATE(lh.ThoiGianHen) = %s
              AND lh.TrangThai != 'Đã hủy'
              {extra_sql}
        """, (ma_bn, ngay_date) + extra_params)
        lich_bn_trong_ngay = cursor.fetchall()
        
        for l_bn in lich_bn_trong_ngay:
            # Tìm ca làm việc của bác sĩ thuộc lịch hẹn cũ đó
            cursor.execute("""
                SELECT ThoiGianBatDau, ThoiGianKetThuc FROM LichLamViec 
                WHERE MaNhanVien = %s AND NgayLamViec = %s
                  AND ThoiGianBatDau <= TIME(%s) AND ThoiGianKetThuc >= TIME(%s)
                LIMIT 1
            """, (l_bn['MaNhanVien'], ngay_date, l_bn['ThoiGianHen'], l_bn['ThoiGianHen']))
            ca_cu = cursor.fetchone()
            
            if ca_cu:
                # Nếu giờ hẹn mới lọt vào khung ca làm việc mà bệnh nhân đã đăng ký bác sĩ khác trực
                if t_bat_dau == ca_cu['ThoiGianBatDau'] and t_ket_thuc == ca_cu['ThoiGianKetThuc']:
                    flash('Lỗi: Bệnh nhân này đã có lịch hẹn với một bác sĩ khác trong cùng ca làm việc này!')
                    cursor.execute("ROLLBACK")
                    return redirect(request.referrer)

        # --- THỰC THI THAO TÁC CSDL KHI ĐÃ ĐẠT ĐẦY ĐỦ RÀNG BUỘC ---
        if action == 'add':
            # Sinh Mã Bệnh Án Mới
            cursor.execute("SELECT MaBenhAn FROM BenhAn ORDER BY MaBenhAn DESC LIMIT 1 FOR UPDATE")
            last_ba = cursor.fetchone()
            num_ba = int(last_ba['MaBenhAn'][2:]) + 1 if last_ba and last_ba['MaBenhAn'] else 1
            ma_ba = f"BA{num_ba:02d}"
            
            cursor.execute("""
                INSERT INTO BenhAn (MaBenhAn, MaBenhNhan, MaNhanVien, NgayKham, ChanDoan, KeHoachDieuTri, TrangThai, GhiChu) 
                VALUES (%s, %s, %s, %s, NULL, NULL, 'Chưa khám', NULL)
            """, (ma_ba, ma_bn, ma_nv, dt_hen))
            
            cursor.execute("""
                INSERT INTO LichHen (MaBenhNhan, MaNhanVien, ThoiGianHen, LyDoKham, TrangThai) 
                VALUES (%s, %s, %s, %s, 'Chờ xác nhận')
            """, (ma_bn, ma_nv, dt_hen, ly_do))
            
            flash('Tạo lịch hẹn thành công! Đã cấp mã hồ sơ và bệnh án mới cho bác sĩ.')
            
        elif action == 'edit':
            cursor.execute("""
                UPDATE LichHen SET MaNhanVien=%s, ThoiGianHen=%s, LyDoKham=%s, TrangThai=%s WHERE MaLichHen=%s
            """, (ma_nv, dt_hen, ly_do, trang_thai, ma_lh))
            flash('Cập nhật lịch hẹn thành công!')
            
        cursor.execute("COMMIT")
        conn.commit()
    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.rollback()
        flash(f'Lỗi hệ thống database: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('lich_hen.danh_sach'))

# --- CẬP NHẬT TRẠNG THÁI NHANH VÀ XÓA ---
@lich_hen_bp.route('/lich-hen/status/<int:id>/<string:status>', methods=['GET'])
def update_status(id, status):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    st_map = {'DaDen': 'Đã đến', 'DaHuy': 'Đã hủy'}
    new_st = st_map.get(status)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE LichHen SET TrangThai = %s WHERE MaLichHen = %s", (new_st, id))
        conn.commit()
        flash(f'Đã chuyển trạng thái thành: {new_st}')
    except Exception as e:
        flash('Lỗi cập nhật trạng thái.')
    finally:
        cursor.close()
        conn.close()
    return redirect(request.referrer)

@lich_hen_bp.route('/lich-hen/delete/<int:id>', methods=['GET'])
def delete(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM LichHen WHERE MaLichHen = %s", (id,))
        conn.commit()
        flash('Đã xóa lịch hẹn!')
    except:
        flash('Không thể xóa lịch hẹn do có dữ liệu liên kết.')
    finally:
        cursor.close()
        conn.close()
    return redirect(request.referrer)