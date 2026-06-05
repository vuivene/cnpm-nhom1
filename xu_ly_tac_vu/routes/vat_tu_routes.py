from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection

vat_tu_bp = Blueprint('vat_tu', __name__)

# =========================================================
# 1. TRANG DANH SÁCH + TÌM KIẾM + BỘ LỌC
# =========================================================
@vat_tu_bp.route('/vat-tu', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    search_query = request.args.get('search', '').strip()
    loai_filter = request.args.get('loai', 'Tất cả')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT MaThuoc AS MaVT, TenThuoc AS TenVatTu, DonViTinh, TonKho AS SoLuongTon, DonGia, 
               'Phòng dược nha khoa' AS NhaCungCap, 10 AS NguongCanhBao, 'Thuốc' AS Loai 
        FROM Thuoc
        UNION ALL
        SELECT MaVatTu AS MaVT, TenVatTu, DonViTinh, SoLuongTon, DonGia, 
               NhaCungCap, NguongCanhBao, 'Dụng cụ tiêu hao' AS Loai 
        FROM VatTu
    """
    
    wrapper_sql = f"SELECT * FROM ({sql}) AS KhoTong WHERE 1=1"
    params = []
    
    if search_query:
        wrapper_sql += " AND (TenVatTu LIKE %s OR MaVT LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
        
    if loai_filter != 'Tất cả':
        wrapper_sql += " AND Loai = %s"
        params.append(loai_filter)
        
    cursor.execute(wrapper_sql, tuple(params))
    ds_kho = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'pages/vat-tu/vat-tu.html', 
        kho=ds_kho, 
        search_query=search_query,
        current_loai=loai_filter
    )

# =========================================================
# 2. ĐIỀU HƯỚNG FORM XEM / THÊM / SỬA (DÙNG CHUNG)
# =========================================================
@vat_tu_bp.route('/vat-tu/form', methods=['GET'])
def form_vat_tu():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.args.get('action', 'add')
    id_vt = request.args.get('id', '')
    
    data = None
    if action in ['view', 'edit'] and id_vt:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if id_vt.startswith('TH'):
            cursor.execute("""
                SELECT MaThuoc AS MaVT, TenThuoc AS TenVatTu, DonViTinh, TonKho AS SoLuongTon, DonGia, 
                       'Phòng dược nha khoa' AS NhaCungCap, 10 AS NguongCanhBao, 'Thuốc' AS Loai 
                FROM Thuoc WHERE MaThuoc = %s
            """, (id_vt,))
        else:
            cursor.execute("""
                SELECT MaVatTu AS MaVT, TenVatTu, DonViTinh, SoLuongTon, DonGia, 
                       NhaCungCap, NguongCanhBao, 'Dụng cụ tiêu hao' AS Loai 
                FROM VatTu WHERE MaVatTu = %s
            """, (id_vt,))
            
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        
    return render_template('pages/vat-tu/them-vat-tu.html', action=action, data=data)

# =========================================================
# 3. XỬ LÝ LƯU HOẶC CẬP NHẬT DỮ LIỆU + CHUYỂN ĐỔI MÃ
# =========================================================
@vat_tu_bp.route('/vat-tu/save', methods=['POST'])
def save_vat_tu():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.form.get('action')
    loai = request.form.get('loai')
    loai_goc = request.form.get('loai_goc')
    ten_vt = request.form.get('ten_vt', '').strip()
    so_luong_raw = request.form.get('so_luong', '0').strip()
    don_vi = request.form.get('don_vi', '').strip()
    don_gia_raw = request.form.get('don_gia', '0').strip()
    ncc = request.form.get('ncc', '').strip()
    nguong_raw = request.form.get('nguong', '0').strip()
    id_vt = request.form.get('ma_vt', '')

    if not all([ten_vt, don_vi, ncc]):
        flash('Lỗi: Tên hàng hóa, Đơn vị tính và Nhà cung cấp không được để trống!')
        return redirect(request.referrer)

    try:
        so_luong = int(so_luong_raw)
        don_gia = float(don_gia_raw)
        nguong = int(nguong_raw)
        if so_luong < 0 or don_gia < 0 or nguong < 0:
            flash('Lỗi: Các thông số Số lượng, Đơn giá, Ngưỡng không được phép là số âm!')
            return redirect(request.referrer)
    except ValueError:
        flash('Lỗi: Định dạng các ô nhập chữ số không hợp lệ!')
        return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("START TRANSACTION")

        # --- NỚI LỎNG ĐIỀU KIỆN: CHỈ CHẶN KHI TRÙNG NHAU 100% TUYỆT ĐỐI ---
        # Sử dụng TRIM() trong SQL để làm sạch dữ liệu trước khi so sánh bằng (=)
        
        # A. Kiểm tra trùng 100% tên trong bảng Thuoc
        sql_chk_thuoc = "SELECT MaThuoc FROM Thuoc WHERE TRIM(TenThuoc) = %s"
        if action == 'edit' and id_vt.startswith('TH') and loai == 'Thuốc':
            sql_chk_thuoc += " AND MaThuoc != %s"
            cursor.execute(sql_chk_thuoc, (ten_vt, id_vt))
        else:
            cursor.execute(sql_chk_thuoc, (ten_vt,))
        if cursor.fetchone():
            flash('Lỗi: Tên hàng hóa này trùng lặp 100% với một thuốc đã có trong danh mục!')
            conn.rollback()
            return redirect(request.referrer)

        # B. Kiểm tra trùng 100% tên trong bảng VatTu
        sql_chk_vattu = "SELECT MaVatTu FROM VatTu WHERE TRIM(TenVatTu) = %s"
        if action == 'edit' and not id_vt.startswith('TH') and loai == 'Dụng cụ tiêu hao':
            sql_chk_vattu += " AND MaVatTu != %s"
            cursor.execute(sql_chk_vattu, (ten_vt, id_vt))
        else:
            cursor.execute(sql_chk_vattu, (ten_vt,))
        if cursor.fetchone():
            flash('Lỗi: Tên hàng hóa này trùng lặp 100% với một vật tư đã có trong danh mục!')
            conn.rollback()
            return redirect(request.referrer)

        # --- TIẾN HÀNH THỰC THI GHI DỮ LIỆU XUỐNG DATABASE ---
        if action == 'add':
            if loai == 'Thuốc':
                cursor.execute("SELECT MaThuoc FROM Thuoc ORDER BY MaThuoc DESC LIMIT 1 FOR UPDATE")
                last = cursor.fetchone()
                new_id = f"TH{int(last[0][2:]) + 1:02d}" if last else "TH01"
                cursor.execute("INSERT INTO Thuoc (MaThuoc, TenThuoc, DonViTinh, DonGia, TonKho) VALUES (%s, %s, %s, %s, %s)", (new_id, ten_vt, don_vi, don_gia, so_luong))
            else:
                cursor.execute("SELECT MaVatTu FROM VatTu ORDER BY MaVatTu DESC LIMIT 1 FOR UPDATE")
                last = cursor.fetchone()
                new_id = f"VT{int(last[0][2:]) + 1:02d}" if last else "VT01"
                cursor.execute("INSERT INTO VatTu (MaVatTu, TenVatTu, DonViTinh, SoLuongTon, DonGia, NhaCungCap, NguongCanhBao) VALUES (%s, %s, %s, %s, %s, %s, %s)", (new_id, ten_vt, don_vi, so_luong, don_gia, ncc, nguong))
            flash(f'Đã nhập kho mặt hàng mới {new_id} thành công!')

        elif action == 'edit':
            # THAY ĐỔI PHÂN LOẠI NHÓM ĐỒNG THỜI ĐỔI MÃ
            if loai != loai_goc:
                if loai == 'Thuốc':
                    cursor.execute("SELECT MaThuoc FROM Thuoc ORDER BY MaThuoc DESC LIMIT 1 FOR UPDATE")
                    last = cursor.fetchone()
                    new_id = f"TH{int(last[0][2:]) + 1:02d}" if last else "TH01"
                    
                    cursor.execute("UPDATE ChiTietHoaDon SET MaThuoc = %s, MaVatTu = NULL WHERE MaVatTu = %s", (new_id, id_vt))
                    cursor.execute("INSERT INTO Thuoc (MaThuoc, TenThuoc, DonViTinh, DonGia, TonKho) VALUES (%s, %s, %s, %s, %s)", (new_id, ten_vt, don_vi, don_gia, so_luong))
                    cursor.execute("DELETE FROM VatTu WHERE MaVatTu = %s", (id_vt,))
                    flash(f'Thay đổi phân loại thành công! Hàng hóa đã được chuyển sang nhóm Thuốc với mã mới: {new_id}')
                else:
                    cursor.execute("SELECT MaVatTu FROM VatTu ORDER BY MaVatTu DESC LIMIT 1 FOR UPDATE")
                    last = cursor.fetchone()
                    new_id = f"VT{int(last[0][2:]) + 1:02d}" if last else "VT01"
                    
                    cursor.execute("UPDATE ChiTietHoaDon SET MaVatTu = %s, MaThuoc = NULL WHERE MaThuoc = %s", (new_id, id_vt))
                    cursor.execute("UPDATE ChiTietDonThuoc SET MaThuoc = %s WHERE MaThuoc = %s", (new_id, id_vt))
                    cursor.execute("INSERT INTO VatTu (MaVatTu, TenVatTu, DonViTinh, SoLuongTon, DonGia, NhaCungCap, NguongCanhBao) VALUES (%s, %s, %s, %s, %s, %s, %s)", (new_id, ten_vt, don_vi, so_luong, don_gia, ncc, nguong))
                    cursor.execute("DELETE FROM Thuoc WHERE MaThuoc = %s", (id_vt,))
                    flash(f'Thay đổi phân loại thành công! Hàng hóa đã được chuyển sang nhóm Vật tư với mã mới: {new_id}')
            else:
                if id_vt.startswith('TH'):
                    cursor.execute("UPDATE Thuoc SET TenThuoc=%s, DonViTinh=%s, TonKho=%s, DonGia=%s WHERE MaThuoc=%s", (ten_vt, don_vi, so_luong, don_gia, id_vt))
                else:
                    cursor.execute("UPDATE VatTu SET TenVatTu=%s, DonViTinh=%s, SoLuongTon=%s, DonGia=%s, NhaCungCap=%s, NguongCanhBao=%s WHERE MaVatTu=%s", (ten_vt, don_vi, so_luong, don_gia, ncc, nguong, id_vt))
                flash(f'Cập nhật thông tin hàng hóa {id_vt} thành công!')

        cursor.execute("COMMIT")
        conn.commit()
    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.rollback()
        flash(f'Lỗi hệ thống CSDL: {e}')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('vat_tu.danh_sach'))

# =========================================================
# 4. TÁC VỤ XÓA MẶT HÀNG
# =========================================================
@vat_tu_bp.route('/vat-tu/xoa/<string:id>', methods=['GET'])
def xoa_vat_tu(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if id.startswith('TH'):
            cursor.execute("DELETE FROM ChiTietHoaDon WHERE MaThuoc = %s", (id,))
            cursor.execute("DELETE FROM ChiTietDonThuoc WHERE MaThuoc = %s", (id,))
            cursor.execute("DELETE FROM Thuoc WHERE MaThuoc = %s", (id,))
        else:
            cursor.execute("DELETE FROM ChiTietHoaDon WHERE MaVatTu = %s", (id,))
            cursor.execute("DELETE FROM VatTu WHERE MaVatTu = %s", (id,))
        conn.commit()
        flash(f'Đã xóa mã hàng {id} khỏi kho dữ liệu.')
    except Exception as e:
        conn.rollback()
        flash(f'Không thể xóa hàng hóa do vướng ràng buộc dữ liệu cũ: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('vat_tu.danh_sach'))