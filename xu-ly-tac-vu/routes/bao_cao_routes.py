from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, session
import mysql.connector
from datetime import datetime, timedelta
import csv
import io

bao_cao_bp = Blueprint('bao_cao', __name__)

def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='QuanLyPhongKhamNhaKhoa'
    )

@bao_cao_bp.route('/bao-cao', methods=['GET'])
def bao_cao_danh_sach():
    if 'loggedin' not in session:
        flash('Vui lòng đăng nhập để xem báo cáo.')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # ==========================================
    # 1. TÌM KIẾM & DANH SÁCH BÁO CÁO
    # ==========================================
    search_query = request.args.get('search', '')
    if search_query:
        cursor.execute("SELECT * FROM BaoCaoChiTieu WHERE MaBaoCao LIKE %s OR LoaiBaoCao LIKE %s ORDER BY ThoiGianKhoiTao DESC", 
                       (f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute("SELECT * FROM BaoCaoChiTieu ORDER BY ThoiGianKhoiTao DESC")
    danh_sach_bc = cursor.fetchall()

    # ==========================================
    # 2. THỐNG KÊ DASHBOARD (ĐÃ SỬA LỖI DOANH THU)
    # ==========================================
    thang_hien_tai = datetime.now().month
    nam_hien_tai = datetime.now().year
    
    # Sửa lỗi doanh thu: Chấp nhận nhiều định dạng trạng thái (Đã thanh toán, Hoàn thành...)
    cursor.execute("""
        SELECT SUM(TongTien) as DoanhThu 
        FROM HoaDon 
        WHERE MONTH(NgayLap) = %s AND YEAR(NgayLap) = %s 
        AND TrangThai IN ('DaThanhToan', 'Đã thanh toán', 'Hoàn thành', '1')
    """, (thang_hien_tai, nam_hien_tai))
    doanh_thu_thang = cursor.fetchone()['DoanhThu'] or 0

    cursor.execute("""
        SELECT COUNT(DISTINCT MaBenhNhan) as KhachMoi 
        FROM HoaDon 
        WHERE MONTH(NgayLap) = %s AND YEAR(NgayLap) = %s
    """, (thang_hien_tai, nam_hien_tai))
    khach_moi = cursor.fetchone()['KhachMoi'] or 0

    cursor.execute("""
        SELECT dv.TenDichVu, COUNT(ct.MaDichVu) as SoLan
        FROM ChiTietHoaDon ct
        JOIN DichVu dv ON ct.MaDichVu = dv.MaDichVu
        JOIN HoaDon hd ON ct.MaHoaDon = hd.MaHoaDon
        WHERE MONTH(hd.NgayLap) = %s AND YEAR(hd.NgayLap) = %s
        GROUP BY dv.TenDichVu
        ORDER BY SoLan DESC LIMIT 1
    """, (thang_hien_tai, nam_hien_tai))
    dv_pho_bien_row = cursor.fetchone()
    dich_vu_pho_bien = dv_pho_bien_row['TenDichVu'] if dv_pho_bien_row else "Chưa có"

    # ==========================================
    # 3. LỊCH LÀM VIỆC (CÓ ĐIỀU HƯỚNG TUẦN)
    # ==========================================
    # Lấy ngày được chọn từ URL (nếu có), mặc định là hôm nay
    selected_date_str = request.args.get('week_date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = datetime.now().date()
    else:
        selected_date = datetime.now().date()

    # Tính toán ngày đầu tuần (Thứ 2) và các ngày trong tuần
    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    dates_of_week = [(start_of_week + timedelta(days=i)) for i in range(7)]
    
    # Tính toán tuần trước và tuần sau cho nút điều hướng
    prev_week = start_of_week - timedelta(days=7)
    next_week = start_of_week + timedelta(days=7)
    
    cursor.execute("""
        SELECT nv.MaNhanVien, nv.HoTen, tk.ChucVu, l.NgayLamViec, l.ThoiGianBatDau, l.ThoiGianKetThuc
        FROM NhanVien nv
        LEFT JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien
        LEFT JOIN LichLamViec l ON nv.MaNhanVien = l.MaNhanVien 
        AND l.NgayLamViec BETWEEN %s AND %s
    """, (start_of_week, dates_of_week[-1]))
    
    lich_raw = cursor.fetchall()
    
    nhan_vien_dict = {}
    today_compare = datetime.now().date()
    for row in lich_raw:
        ma_nv = row['MaNhanVien']
        if ma_nv not in nhan_vien_dict:
            nhan_vien_dict[ma_nv] = {
                'HoTen': row['HoTen'],
                'ChucVu': row['ChucVu'] or 'Nhân viên',
                'Lich': {}
            }
        if row['NgayLamViec']:
            trang_thai = 'da_lam' if row['NgayLamViec'] < today_compare else 'co_lich'
            nhan_vien_dict[ma_nv]['Lich'][row['NgayLamViec']] = {
                'tg': f"{row['ThoiGianBatDau']} - {row['ThoiGianKetThuc']}",
                'status': trang_thai
            }

    cursor.close()
    conn.close()

    # Đã sửa lại đường dẫn theo đúng cấu trúc thư mục của bạn
    return render_template('pages/bao-cao/bao-cao.html', 
                           danh_sach=danh_sach_bc, 
                           doanh_thu_thang=doanh_thu_thang,
                           khach_moi=khach_moi,
                           dich_vu_pho_bien=dich_vu_pho_bien,
                           dates_of_week=dates_of_week,
                           start_of_week=start_of_week,
                           prev_week=prev_week,
                           next_week=next_week,
                           lich_nhan_vien=nhan_vien_dict)

@bao_cao_bp.route('/bao-cao/them', methods=['GET', 'POST'])
def bao_cao_them():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        loai_bc = request.form['loai_bao_cao']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. TỰ TĂNG MÃ BÁO CÁO (BC01, BC02,...)
        # Lấy mã báo cáo lớn nhất hiện có
        cursor.execute("SELECT MAX(CAST(SUBSTRING(MaBaoCao, 3) AS UNSIGNED)) as MaxID FROM BaoCaoChiTieu")
        result = cursor.fetchone()
        next_id = (result['MaxID'] or 0) + 1
        ma_bc = f"BC{next_id:02d}" # :02d đảm bảo luôn có 2 chữ số (BC01, BC02,...)
        
        # 2. TÍNH TOÁN DỮ LIỆU
        today = datetime.now()
        # (Giữ nguyên logic tính doanh thu của bạn ở đây...)
        if loai_bc == 'Ngày': date_cond = "DATE(NgayLap) = CURDATE()"
        elif loai_bc == 'Tuần': date_cond = "YEARWEEK(NgayLap, 1) = YEARWEEK(CURDATE(), 1)"
        elif loai_bc == 'Tháng': date_cond = "MONTH(NgayLap) = MONTH(CURDATE()) AND YEAR(NgayLap) = YEAR(CURDATE())"
        else: date_cond = "1=1"

        cursor.execute(f"""
            SELECT SUM(TongTien) as DoanhThu, COUNT(DISTINCT MaBenhNhan) as SoKhach
            FROM HoaDon 
            WHERE {date_cond} AND TrangThai IN ('DaThanhToan', 'Đã thanh toán', 'Hoàn thành', '1')
        """)
        stats = cursor.fetchone()
        doanh_thu = stats['DoanhThu'] or 0
        khach = stats['SoKhach'] or 0

        # 3. LƯU VÀO CSDL
        cursor.execute("""
            INSERT INTO BaoCaoChiTieu (MaBaoCao, LoaiBaoCao, ThoiGianKhoiTao, TongDoanhThu, LuongKhachHang)
            VALUES (%s, %s, %s, %s, %s)
        """, (ma_bc, loai_bc, today, doanh_thu, khach))
        
        conn.commit()
        cursor.close()
        conn.close()
        flash(f'Đã tạo báo cáo {ma_bc} thành công!', 'success')
        return redirect(url_for('bao_cao.bao_cao_danh_sach'))

    return render_template('pages/bao-cao/them-bao-cao.html', mode='them', bc=None)

@bao_cao_bp.route('/bao-cao/xem/<ma_bc>', methods=['GET'])
def bao_cao_xem(ma_bc):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM BaoCaoChiTieu WHERE MaBaoCao = %s", (ma_bc,))
    bc = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('pages/bao-cao/them-bao-cao.html', mode='xem', bc=bc)

@bao_cao_bp.route('/bao-cao/xoa/<ma_bc>', methods=['POST'])
def bao_cao_xoa(ma_bc):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM BaoCaoChiTieu WHERE MaBaoCao = %s", (ma_bc,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Đã xóa báo cáo!', 'success')
    return redirect(url_for('bao_cao.bao_cao_danh_sach'))

@bao_cao_bp.route('/bao-cao/xuat-excel')
def bao_cao_xuat_excel():
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM BaoCaoChiTieu ORDER BY ThoiGianKhoiTao DESC")
    rows = cursor.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Mã BC', 'Loại Báo Cáo', 'Thời Gian', 'Tổng Doanh Thu', 'Lượng Khách Hàng'])
    for row in rows:
        writer.writerow([row['MaBaoCao'], row['LoaiBaoCao'], row['ThoiGianKhoiTao'], row['TongDoanhThu'], row['LuongKhachHang']])
    
    response = Response(output.getvalue().encode('utf-8-sig'), mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = 'attachment; filename=LichSuBaoCao.csv'
    return response

@bao_cao_bp.route('/bao-cao/xuat-pdf/<ma_bc>')
def bao_cao_xuat_pdf(ma_bc):
    if 'loggedin' not in session: return redirect(url_for('login'))
    return f"<script>window.print(); setTimeout(() => {{ window.location.href='/bao-cao'; }}, 1000);</script><h1>Báo cáo PDF {ma_bc}</h1>"