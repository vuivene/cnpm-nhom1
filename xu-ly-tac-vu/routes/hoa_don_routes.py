from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db_config import get_db_connection
from datetime import datetime

hoa_don_bp = Blueprint('hoa_don', __name__)

# =========================================================
# ROUTE DANH SÁCH HÓA ĐƠN
# =========================================================
@hoa_don_bp.route('/hoa-don', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    search_query = request.args.get('search', '').strip()
    trang_thai_filter = request.args.get('trang_thai', 'Tất cả')
    thang_filter = request.args.get('thang', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = "SELECT hd.*, bn.HoTen AS TenBenhNhan FROM HoaDon hd JOIN BenhNhan bn ON hd.MaBenhNhan = bn.MaBenhNhan WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (hd.MaHoaDon LIKE %s OR bn.HoTen LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if trang_thai_filter != 'Tất cả':
        sql += " AND hd.TrangThai = %s"
        params.append(trang_thai_filter)
    if thang_filter: 
        sql += " AND DATE_FORMAT(hd.NgayLap, '%Y-%m') = %s"
        params.append(thang_filter)
        
    sql += " ORDER BY hd.NgayLap DESC"
    cursor.execute(sql, tuple(params))
    ds_hoa_don = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('pages/hoa-don/hoa-don.html', hoa_don=ds_hoa_don, search_query=search_query, current_trang_thai=trang_thai_filter, current_thang=thang_filter)

# =========================================================
# TRANG QUẢN LÝ DANH SÁCH ĐƠN THUỐC CỦA BN
# =========================================================
@hoa_don_bp.route('/hoa-don/don-thuoc-benh-nhan/<string:ma_bn>', methods=['GET'])
def quan_ly_don_thuoc(ma_bn):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT dt.MaDonThuoc, dt.GhiChu, ba.MaBenhAn, ba.NgayKham, 
               dt.MaHoaDon as MaHoaDonLK, 
               hd.TrangThai as TrangThaiHD
        FROM DonThuoc dt
        JOIN BenhAn ba ON dt.MaBenhAn = ba.MaBenhAn
        LEFT JOIN HoaDon hd ON dt.MaHoaDon = hd.MaHoaDon
        WHERE ba.MaBenhNhan = %s
        ORDER BY dt.MaDonThuoc DESC
    """
    cursor.execute(sql, (ma_bn,))
    ds_don_thuoc = cursor.fetchall()
    
    cursor.execute("SELECT * FROM BenhNhan WHERE MaBenhNhan = %s", (ma_bn,))
    benh_nhan = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as count FROM BenhAn WHERE MaBenhNhan = %s AND TrangThai = 'Đang điều trị'", (ma_bn,))
    dang_dieu_tri = cursor.fetchone()['count'] > 0
    
    cursor.close()
    conn.close()
    return render_template('pages/hoa-don/danh-sach-don-thuoc.html', benh_nhan=benh_nhan, don_thuoc=ds_don_thuoc, dang_dieu_tri=dang_dieu_tri)

# =========================================================
# TẠO ĐƠN THUỐC & KIỂM TRA GIỚI HẠN TỒN KHO THUỐC
# =========================================================
@hoa_don_bp.route('/hoa-don/tao-don/<string:ma_bn>', methods=['GET', 'POST'])
def tao_don_thuoc(ma_bn):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        ma_nv = session.get('id', 'NV02')
        ghi_chu = request.form.get('ghi_chu', '')
        dich_vu_ids = request.form.getlist('dich_vu_ids[]')
        tinh_phi_ids = request.form.getlist('tinh_phi_dv_ids[]')
        thuoc_ids = request.form.getlist('thuoc_ids[]')
        sl_thuocs = request.form.getlist('sl_thuocs[]')
        
        try:
            cursor.execute("START TRANSACTION")
            cursor.execute("SELECT MaBenhAn FROM BenhAn WHERE MaBenhNhan = %s AND TrangThai = 'Đang điều trị' LIMIT 1", (ma_bn,))
            ba = cursor.fetchone()
            if not ba: raise Exception("Bệnh nhân không có bệnh án Đang điều trị!")
            ma_ba = ba['MaBenhAn']

            def get_new_id(prefix, table, col):
                cursor.execute(f"SELECT {col} FROM {table} ORDER BY {col} DESC LIMIT 1 FOR UPDATE")
                last = cursor.fetchone()
                num = int(last[col][len(prefix):]) + 1 if last and last[col] else 1
                return f"{prefix}{num:02d}"

            new_dt = get_new_id("DT", "DonThuoc", "MaDonThuoc")
            new_hd = get_new_id("HD", "HoaDon", "MaHoaDon")

            cursor.execute("INSERT INTO HoaDon (MaHoaDon, MaBenhNhan, MaNhanVien, NgayLap, TrangThai, TongTien, ThueVAT) VALUES (%s, %s, %s, NOW(), 'Chưa thanh toán', 0, 0)", 
                           (new_hd, ma_bn, ma_nv))
            cursor.execute("INSERT INTO DonThuoc (MaDonThuoc, MaBenhAn, GhiChu, MaHoaDon) VALUES (%s, %s, %s, %s)", 
                           (new_dt, ma_ba, ghi_chu, new_hd))

            tong_tien = 0.0
            tong_vat = 0.0
            
            for dv_id in dich_vu_ids:
                cursor.execute("SELECT DonGia FROM DichVu WHERE MaDichVu = %s", (dv_id,))
                gia = float(cursor.fetchone()['DonGia'])
                gia_dv = gia if dv_id in tinh_phi_ids else 0.0
                tong_tien += gia_dv
                cursor.execute("INSERT INTO ChiTietHoaDon (MaHoaDon, MaDichVu, SoLuong, DonGia, ThanhTien) VALUES (%s, %s, 1, %s, %s)", (new_hd, dv_id, gia_dv, gia_dv))
                
            # Duyệt danh sách thuốc để kiểm tra điều kiện giới hạn số lượng tồn kho
            for t_id, sl in zip(thuoc_ids, sl_thuocs):
                sl = int(sl)
                cursor.execute("SELECT DonGia, TonKho, TenThuoc FROM Thuoc WHERE MaThuoc = %s FOR UPDATE", (t_id,))
                thuoc_info = cursor.fetchone()
                
                # Nghiệp vụ: Số thuốc thêm vô không được quá số thuốc đang có
                if sl > thuoc_info['TonKho']:
                    raise Exception(f"Thuốc '{thuoc_info['TenThuoc']}' không đủ số lượng trong kho (Yêu cầu: {sl}, Hiện có: {thuoc_info['TonKho']})")
                
                gia_t = float(thuoc_info['DonGia'])
                thanh_tien_t = gia_t * sl
                vat_t = thanh_tien_t * 0.05
                tong_tien += (thanh_tien_t + vat_t)
                tong_vat += vat_t
                
                cursor.execute("INSERT INTO ChiTietDonThuoc (MaDonThuoc, MaThuoc, SoLuong) VALUES (%s, %s, %s)", (new_dt, t_id, sl))
                cursor.execute("INSERT INTO ChiTietHoaDon (MaHoaDon, MaThuoc, SoLuong, DonGia, ThanhTien) VALUES (%s, %s, %s, %s, %s)", (new_hd, t_id, sl, gia_t, thanh_tien_t))
                
            cursor.execute("UPDATE HoaDon SET TongTien = %s, ThueVAT = %s WHERE MaHoaDon = %s", (tong_tien, tong_vat, new_hd))
            cursor.execute("COMMIT")
            conn.commit()
            flash('Tạo đơn thuốc và hóa đơn thành công!')
            return redirect(url_for('hoa_don.quan_ly_don_thuoc', ma_bn=ma_bn))
        except Exception as e:
            cursor.execute("ROLLBACK")
            conn.rollback()
            flash(f'Lỗi: {e}')
            return redirect(request.referrer)

    # GET Form
    cursor.execute("SELECT DISTINCT cthd.MaDichVu FROM ChiTietHoaDon cthd JOIN HoaDon hd ON cthd.MaHoaDon = hd.MaHoaDon WHERE hd.MaBenhNhan = %s AND hd.TrangThai = 'Đã thanh toán'", (ma_bn,))
    paid_services = [row['MaDichVu'] for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM BenhNhan WHERE MaBenhNhan = %s", (ma_bn,))
    benh_nhan = cursor.fetchone()
    cursor.execute("SELECT * FROM DichVu WHERE TinhTrang = 1")
    dich_vu = cursor.fetchall()
    cursor.execute("SELECT * FROM Thuoc WHERE TonKho > 0")
    thuoc = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('pages/hoa-don/tao-don-thuoc.html', benh_nhan=benh_nhan, dich_vu=dich_vu, thuoc=thuoc, paid_services=paid_services)

# =========================================================
# XÓA ĐƠN THUỐC
# =========================================================
@hoa_don_bp.route('/hoa-don/xoa-don-thuoc/<string:id>', methods=['GET'])
def xoa_don_thuoc(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT MaHoaDon FROM DonThuoc WHERE MaDonThuoc = %s", (id,))
        dt = cursor.fetchone()
        if not dt:
            flash('Đơn thuốc không tồn tại!')
            return redirect(request.referrer)
        
        ma_hd = dt['MaHoaDon']
        cursor.execute("SELECT TrangThai FROM HoaDon WHERE MaHoaDon = %s", (ma_hd,))
        hd = cursor.fetchone()
        
        if hd and hd['TrangThai'] == 'Đã thanh toán':
            flash('Không thể xóa: Hóa đơn liên quan đã hoàn tất thanh toán!')
            return redirect(request.referrer)
        
        cursor.execute("DELETE FROM ChiTietDonThuoc WHERE MaDonThuoc = %s", (id,))
        cursor.execute("DELETE FROM ChiTietHoaDon WHERE MaHoaDon = %s", (ma_hd,))
        cursor.execute("DELETE FROM DonThuoc WHERE MaDonThuoc = %s", (id,))
        cursor.execute("DELETE FROM HoaDon WHERE MaHoaDon = %s", (ma_hd,))
        conn.commit()
        flash('Đã xóa đơn thuốc và hóa đơn liên quan!')
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi khi xóa: {e}')
    finally:
        cursor.close()
        conn.close()
    return redirect(request.referrer)

# =========================================================
# FORM CHỈNH SỬA HÓA ĐƠN / ĐƠN THUỐC
# =========================================================
@hoa_don_bp.route('/hoa-don/form/<string:id>', methods=['GET'])
def form_hoa_don(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    action = request.args.get('action', 'view')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT hd.*, bn.HoTen AS TenBenhNhan FROM HoaDon hd JOIN BenhNhan bn ON hd.MaBenhNhan = bn.MaBenhNhan WHERE MaHoaDon = %s", (id,))
    hoa_don = cursor.fetchone()
    
    if action == 'edit' and hoa_don['TrangThai'] == 'Đã thanh toán':
        flash('Hóa đơn đã thanh toán, chỉ được phép xem.')
        action = 'view'
    
    cursor.execute("SELECT ct.*, dv.TenDichVu FROM ChiTietHoaDon ct JOIN DichVu dv ON ct.MaDichVu = dv.MaDichVu WHERE ct.MaHoaDon = %s AND ct.MaDichVu IS NOT NULL", (id,))
    ds_dich_vu = cursor.fetchall()
    
    cursor.execute("SELECT ct.*, t.TenThuoc FROM ChiTietHoaDon ct JOIN Thuoc t ON ct.MaThuoc = t.MaThuoc WHERE ct.MaHoaDon = %s AND ct.MaThuoc IS NOT NULL", (id,))
    ds_thuoc = cursor.fetchall()
    ghi_chu = ""
    
    cursor.execute("SELECT * FROM Thuoc WHERE TonKho > 0")
    all_thuoc = cursor.fetchall()
    
    cursor.execute("SELECT dt.GhiChu FROM DonThuoc dt JOIN BenhAn ba ON dt.MaBenhAn = ba.MaBenhAn WHERE ba.MaBenhNhan = %s ORDER BY dt.MaDonThuoc DESC LIMIT 1", (hoa_don['MaBenhNhan'],))
    dt_info = cursor.fetchone()
    if dt_info: ghi_chu = dt_info['GhiChu']
    cursor.close()
    conn.close()
    return render_template('pages/hoa-don/them-hoa-don.html', action=action, data=hoa_don, dich_vu=ds_dich_vu, thuoc=ds_thuoc, ghi_chu=ghi_chu, all_thuoc=all_thuoc)

# =========================================================
# LƯU CẬP NHẬT HOẶC THÊM THUỐC MỚI VÀO HÓA ĐƠN ĐANG CHỜ
# =========================================================
@hoa_don_bp.route('/hoa-don/save', methods=['POST'])
def save_hoa_don():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_hd = request.form.get('ma_hd')
    ghi_chu = request.form.get('ghi_chu', '')
    thuoc_ids = request.form.getlist('thuoc_ids[]')
    sl_thuocs = request.form.getlist('sl_thuocs[]')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("START TRANSACTION")
        
        # Xóa chi tiết thuốc cũ để tính toán nạp lại tập hợp mới
        cursor.execute("DELETE FROM ChiTietHoaDon WHERE MaHoaDon = %s AND MaThuoc IS NOT NULL", (ma_hd,))
        
        tong_tien_thuoc = 0
        tong_vat_thuoc = 0
        
        for t_id, sl in zip(thuoc_ids, sl_thuocs):
            sl = int(sl)
            cursor.execute("SELECT DonGia, TonKho, TenThuoc FROM Thuoc WHERE MaThuoc = %s FOR UPDATE", (t_id,))
            thuoc_info = cursor.fetchone()
            
            # Nghiệp vụ: Số thuốc thêm vô không được quá số thuốc đang có
            if sl > thuoc_info['TonKho']:
                raise Exception(f"Thuốc '{thuoc_info['TenThuoc']}' không đủ số lượng trong kho (Yêu cầu: {sl}, Hiện có: {thuoc_info['TonKho']})")
                
            gia_t = float(thuoc_info['DonGia'])
            thanh_tien = gia_t * sl
            vat = thanh_tien * 0.05
            tong_tien_thuoc += (thanh_tien + vat)
            tong_vat_thuoc += vat
            
            cursor.execute("INSERT INTO ChiTietHoaDon (MaHoaDon, MaThuoc, SoLuong, DonGia, ThanhTien) VALUES (%s, %s, %s, %s, %s)", (ma_hd, t_id, sl, gia_t, thanh_tien))
            
        cursor.execute("SELECT SUM(ThanhTien) as TongDV FROM ChiTietHoaDon WHERE MaHoaDon = %s AND MaDichVu IS NOT NULL", (ma_hd,))
        tong_dv = float(cursor.fetchone()['TongDV'] or 0)
        tong_tien_moi = tong_dv + tong_tien_thuoc
        
        cursor.execute("UPDATE HoaDon SET TongTien = %s, ThueVAT = %s WHERE MaHoaDon = %s", (tong_tien_moi, tong_vat_thuoc, ma_hd))
        cursor.execute("UPDATE DonThuoc dt JOIN BenhAn ba ON dt.MaBenhAn = ba.MaBenhAn JOIN HoaDon hd ON ba.MaBenhNhan = hd.MaBenhNhan SET dt.GhiChu = %s WHERE hd.MaHoaDon = %s", (ghi_chu, ma_hd))
        
        cursor.execute("COMMIT")
        conn.commit()
        flash('Đã cập nhật đơn thuốc thành công!')
    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.rollback()
        flash(f'Lỗi Cập nhật: {e}')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('hoa_don.danh_sach'))

# =========================================================
# XÁC NHẬN THANH TOÁN (TRỪ TỒN KHO THUỐC THỰC TẾ)
# =========================================================
@hoa_don_bp.route('/hoa-don/xac-nhan/<string:id>', methods=['GET'])
def xac_nhan(id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("START TRANSACTION")
        
        # 1. Kiểm tra trạng thái hiện tại của hóa đơn tránh trừ kho hai lần
        cursor.execute("SELECT TrangThai FROM HoaDon WHERE MaHoaDon = %s FOR UPDATE", (id,))
        hd_status = cursor.fetchone()
        if not hd_status:
            raise Exception("Hóa đơn không tồn tại!")
        if hd_status['TrangThai'] == 'Đã thanh toán':
            raise Exception("Hóa đơn này đã được thanh toán từ trước!")
            
        # 2. Lấy danh sách toàn bộ các loại thuốc đính kèm trong chi tiết hóa đơn này
        cursor.execute("SELECT MaThuoc, SoLuong FROM ChiTietHoaDon WHERE MaHoaDon = %s AND MaThuoc IS NOT NULL", (id,))
        ds_thuoc_mua = cursor.fetchall()
        
        # 3. Tiến hành kiểm tra và trừ kho thuốc thực tế
        for item in ds_thuoc_mua:
            m_thuoc = item['MaThuoc']
            qty = item['SoLuong']
            
            cursor.execute("SELECT TonKho, TenThuoc FROM Thuoc WHERE MaThuoc = %s FOR UPDATE", (m_thuoc,))
            t_info = cursor.fetchone()
            
            if t_info['TonKho'] < qty:
                raise Exception(f"Thanh toán thất bại! Thuốc '{t_info['TenThuoc']}' không đủ hàng xuất kho (Yêu cầu: {qty}, Hiện có: {t_info['TonKho']})")
                
            # Khấu trừ số lượng vào CSDL
            cursor.execute("UPDATE Thuoc SET TonKho = TonKho - %s WHERE MaThuoc = %s", (qty, m_thuoc))
            
        # 4. Cập nhật trạng thái hóa đơn
        cursor.execute("UPDATE HoaDon SET TrangThai = 'Đã thanh toán', PhuongThucThanhToan = 'Tiền mặt' WHERE MaHoaDon = %s", (id,))
        
        cursor.execute("COMMIT")
        conn.commit()
        flash(f'Đã xác nhận thanh toán hoàn tất! Toàn bộ thuốc đã được trừ kho trực tiếp.')
    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.rollback()
        flash(f'Lỗi xử lý thanh toán: {e}')
    finally:
        cursor.close()
        conn.close()
    return redirect(request.referrer)

@hoa_don_bp.route('/hoa-don/in/<string:id>', methods=['GET'])
def in_hoa_don(id):
    return f"<script>window.print(); setTimeout(()=>window.history.back(), 1000);</script><h1>Đang in hóa đơn {id}...</h1>"