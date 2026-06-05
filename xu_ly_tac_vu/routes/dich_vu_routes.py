from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection

dich_vu_bp = Blueprint('dich_vu', __name__)

# =========================================================
# 1. TRANG DANH SÁCH + TÌM KIẾM + BỘ LỌC + SẮP XẾP GIÁ CHÚNG
# =========================================================
@dich_vu_bp.route('/dich-vu', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    search_query = request.args.get('search', '').strip()
    tinh_trang_filter = request.args.get('tinh_trang', 'Tất cả')
    sap_xep_filter = request.args.get('sap_xep', 'tang_dan')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = "SELECT * FROM DichVu WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (TenDichVu LIKE %s OR MaDichVu LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
        
    if tinh_trang_filter != 'Tất cả':
        if tinh_trang_filter == 'Đang cung cấp':
            sql += " AND TinhTrang = 1"
        elif tinh_trang_filter == 'Ngừng cung cấp':
            sql += " AND TinhTrang = 0"
            
    if sap_xep_filter == 'tang_dan':
        sql += " ORDER BY DonGia ASC"
    elif sap_xep_filter == 'giam_dan':
        sql += " ORDER BY DonGia DESC"
        
    cursor.execute(sql, tuple(params))
    ds_dich_vu = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'pages/dich-vu/dich-vu.html',
        dich_vu=ds_dich_vu,
        search_query=search_query,
        current_tinh_trang=tinh_trang_filter,
        current_sap_xep=sap_xep_filter
    )

# =========================================================
# 2. ĐIỀU HƯỚNG FORM XEM / THÊM / SỬA (DÙNG CHUNG)
# =========================================================
@dich_vu_bp.route('/dich-vu/form', methods=['GET'])
def form_dich_vu():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.args.get('action', 'add')
    ma_dv = request.args.get('id', '')
    
    data = None
    if action in ['view', 'edit'] and ma_dv:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM DichVu WHERE MaDichVu = %s", (ma_dv,))
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        
    return render_template('pages/dich-vu/them-dich-vu.html', action=action, data=data)

# =========================================================
# 3. XỬ LÝ LƯU HOẶC CẬP NHẬT DỮ LIỆU XUỐNG DATABASE
# =========================================================
@dich_vu_bp.route('/dich-vu/save', methods=['POST'])
def save_dich_vu():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.form.get('action')
    ten_dv = request.form.get('ten_dv', '').strip()
    don_gia_raw = request.form.get('don_gia', '').strip()
    tinh_trang = request.form.get('tinh_trang')
    chi_tiet = request.form.get('chi_tiet', '').strip()

    # --- TẦNG VALIDATION AN TOÀN PHÍA SERVER ---
    if not ten_dv or not don_gia_raw:
        flash('Lỗi: Vui lòng điền đầy đủ thông tin bắt buộc có dấu (*) !')
        return redirect(request.referrer)

    if len(ten_dv) > 150:
        flash('Lỗi: Tên dịch vụ không được phép vượt quá 150 ký tự.')
        return redirect(request.referrer)

    try:
        don_gia = float(don_gia_raw)
        if don_gia < 0:
            flash('Lỗi: Đơn giá dịch vụ không được phép nhỏ hơn 0 VNĐ.')
            return redirect(request.referrer)
    except ValueError:
        flash('Lỗi: Đơn giá không đúng định dạng số.')
        return redirect(request.referrer)

    if len(chi_tiet) > 500:
        flash('Lỗi: Chi tiết dịch vụ không được phép vượt quá 500 ký tự.')
        return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if action == 'add':
            cursor.execute("SELECT MaDichVu FROM DichVu ORDER BY MaDichVu DESC LIMIT 1")
            last_dv = cursor.fetchone()
            new_ma_dv = f"DV{int(last_dv[0][2:]) + 1:02d}" if last_dv else "DV01"

            cursor.execute("""
                INSERT INTO DichVu (MaDichVu, TenDichVu, ChiTiet, DonGia, TinhTrang)
                VALUES (%s, %s, %s, %s, %s)
            """, (new_ma_dv, ten_dv, chi_tiet, don_gia, tinh_trang))
            flash(f'Thêm mới dịch vụ {new_ma_dv} thành công!')

        elif action == 'edit':
            ma_dv = request.form.get('ma_dv')
            cursor.execute("""
                UPDATE DichVu 
                SET TenDichVu=%s, ChiTiet=%s, DonGia=%s, TinhTrang=%s
                WHERE MaDichVu=%s
            """, (ten_dv, chi_tiet, don_gia, tinh_trang, ma_dv))
            flash(f'Cập nhật thông tin dịch vụ {ma_dv} thành công!')

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi hệ thống CSDL: {e}')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dich_vu.danh_sach'))

# =========================================================
# 4. TÁC VỤ XÓA DỊCH VỤ
# =========================================================
@dich_vu_bp.route('/dich-vu/xoa/<string:id>', methods=['GET'])
def xoa_dich_vu(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ChiTietHoaDon WHERE MaDichVu = %s", (id,))
        cursor.execute("DELETE FROM DichVu WHERE MaDichVu = %s", (id,))
        conn.commit()
        flash(f'Đã xóa dịch vụ {id} khỏi danh sách thành công.')
    except Exception as e:
        conn.rollback()
        flash(f'Không thể xóa dịch vụ này do vướng dữ liệu hóa đơn cũ: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('dich_vu.danh_sach'))