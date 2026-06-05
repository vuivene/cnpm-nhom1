from flask import Flask, render_template, request, redirect, url_for, flash, session
# Import thêm hàm chuyên dụng check_password_hash để bóc tách Salt và đối chiếu mật khẩu băm
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'stu_nha_khoa_secret_key'

# =========================================================
# ĐĂNG KÝ CÁC BLUEPRINT PHÂN HỆ ĐỂ ĐỊNH TUYẾN ĐỘNG
# =========================================================
from routes.nhan_vien_routes import nhan_vien_bp  
app.register_blueprint(nhan_vien_bp)              

from routes.benh_nhan_routes import benh_nhan_bp
app.register_blueprint(benh_nhan_bp)

from routes.vat_tu_routes import vat_tu_bp
app.register_blueprint(vat_tu_bp)

from routes.dich_vu_routes import dich_vu_bp
app.register_blueprint(dich_vu_bp)

from routes.hoa_don_routes import hoa_don_bp
app.register_blueprint(hoa_don_bp)

from routes.lich_lam_viec_routes import lich_lam_viec_bp
app.register_blueprint(lich_lam_viec_bp)

from routes.lich_hen_routes import lich_hen_bp
app.register_blueprint(lich_hen_bp)

from routes.bao_cao_routes import bao_cao_bp
app.register_blueprint(bao_cao_bp)

from routes.cai_dat_routes import cai_dat_bp
app.register_blueprint(cai_dat_bp)

# =========================================================
# TUYẾN ĐƯỜNG GỐC (INDEX) - XỬ LÝ ĐIỀU HƯỚNG MẪU
# =========================================================
@app.route('/')
def index():
    if 'loggedin' in session:
        return redirect(url_for('bang_quan_tri'))
    else:
        return redirect(url_for('login'))


# =========================================================
# API ĐĂNG NHẬP (ĐÃ CẬP NHẬT KIỂM TRA MẬT KHẨU BĂM)
# =========================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        _username = request.form['username']
        _password = request.form['password']

        from db_config import get_db_connection
        conn = get_db_connection()
        if not conn:
            flash('Không thể kết nối đến cơ sở dữ liệu!')
            return render_template('pages/auth/dang-nhap.html')

        cursor = conn.cursor(dictionary=True)
        
        # GIẢI PHÁP AN TOÀN: Chỉ lọc theo TenDangNhap, không đối chiếu chuỗi mật khẩu thô bằng lệnh SQL
        query = "SELECT * FROM TaiKhoan WHERE TenDangNhap = %s"
        cursor.execute(query, (_username,))
        account = cursor.fetchone()

        cursor.close()
        conn.close()

        # Thực hiện bóc tách Salt đính kèm bên trong chuỗi băm của CSDL để kiểm tra mật khẩu gõ vào
        if account and check_password_hash(account['MatKhau'], _password):
            if account['TinhTrang'] == 1:
                session['loggedin'] = True
                session['id'] = account['MaNhanVien']
                session['username'] = account['TenDangNhap']
                session['role'] = account['ChucVu']
                
                return redirect(url_for('bang_quan_tri'))
            else:
                flash('Tài khoản của bạn hiện đang bị khóa!')
        else:
            flash('Tên đăng nhập hoặc mật khẩu không chính xác!')

    return render_template('pages/auth/dang-nhap.html')


# =========================================================
# TRANG BẢNG QUẢN TRỊ (TỔNG QUAN)
# =========================================================
@app.route('/bang-quan-tri')
def bang_quan_tri():
    if 'loggedin' not in session:
        flash('Vui lòng đăng nhập để truy cập hệ thống.')
        return redirect(url_for('login'))

    from db_config import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Số lịch hẹn hôm nay
    cursor.execute("SELECT COUNT(*) AS cnt FROM LichHen WHERE DATE(ThoiGianHen) = CURDATE()")
    lich_hen_hom_nay = cursor.fetchone()['cnt']

    # 2. Bệnh nhân khám trong tháng
    cursor.execute("SELECT COUNT(DISTINCT MaBenhNhan) AS cnt FROM BenhAn WHERE MONTH(NgayKham) = MONTH(CURDATE()) AND YEAR(NgayKham) = YEAR(CURDATE())")
    benh_nhan_thang = cursor.fetchone()['cnt']

    # 3. Doanh thu trong tháng
    cursor.execute("SELECT SUM(TongTien) AS total FROM HoaDon WHERE TrangThai = 'Đã thanh toán' AND MONTH(NgayLap) = MONTH(CURDATE()) AND YEAR(NgayLap) = YEAR(CURDATE())")
    doanh_thu_thang = cursor.fetchone()['total']
    if doanh_thu_thang is None:
        doanh_thu_thang = 0

    # 4. VẬT TƯ SẮP HẾT: Gộp chung cả số lượng từ bảng VatTu và bảng Thuoc theo ngưỡng CSDL thực tế
    cursor.execute("""
        SELECT 
            (SELECT COUNT(*) FROM VatTu WHERE SoLuongTon <= NguongCanhBao) + 
            (SELECT COUNT(*) FROM Thuoc WHERE TonKho <= 5) AS cnt
    """)
    vat_tu_sap_het_count = cursor.fetchone()['cnt']

    # 5. Danh sách lịch hẹn hôm nay
    cursor.execute("""
        SELECT lh.ThoiGianHen, bn.HoTen AS TenBenhNhan, nv.HoTen AS TenBacSi, lh.TrangThai
        FROM LichHen lh
        JOIN BenhNhan bn ON lh.MaBenhNhan = bn.MaBenhNhan
        JOIN NhanVien nv ON lh.MaNhanVien = nv.MaNhanVien
        WHERE DATE(lh.ThoiGianHen) = CURDATE()
        ORDER BY lh.ThoiGianHen ASC
        LIMIT 6
    """)
    danh_sach_lich_hen = cursor.fetchall()

    # 6. THÔNG BÁO HỆ THỐNG: Sử dụng UNION ALL để gộp chung danh sách Thuốc và Vật tư y tế sắp hết kho kho động
    cursor.execute("""
        SELECT TenVatTu AS TenVatTu, SoLuongTon AS SoLuongTon FROM VatTu WHERE SoLuongTon <= NguongCanhBao
        UNION ALL
        SELECT TenThuoc AS TenVatTu, TonKho AS SoLuongTon FROM Thuoc WHERE TonKho <= 5
    """)
    thong_bao_vat_tu = cursor.fetchall()

    # 7. Thông báo: Hóa đơn chưa thanh toán
    cursor.execute("""
        SELECT hd.MaHoaDon, bn.HoTen AS TenBenhNhan
        FROM HoaDon hd
        JOIN BenhNhan bn ON hd.MaBenhNhan = bn.MaBenhNhan
        WHERE hd.TrangThai = 'Chưa thanh toán'
        ORDER BY hd.NgayLap DESC
        LIMIT 5
    """)
    thong_bao_hoa_don = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('bang-quan-tri.html',
                           lich_hen_hom_nay=lich_hen_hom_nay,
                           benh_nhan_thang=benh_nhan_thang,
                           doanh_thu_thang=doanh_thu_thang,
                           vat_tu_sap_het_count=vat_tu_sap_het_count,
                           danh_sach_lich_hen=danh_sach_lich_hen,
                           thong_bao_vat_tu=thong_bao_vat_tu,
                           thong_bao_hoa_don=thong_bao_hoa_don)

# =========================================================
# API ĐĂNG XUẤT
# =========================================================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Chạy trên môi trường Local Host Development
    app.run(host='127.0.0.1', port=5000, debug=True)