from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db_config import get_db_connection
from werkzeug.security import generate_password_hash
from datetime import date

nhan_vien_bp = Blueprint('nhan_vien', __name__)

# =========================================================
# 1. TRANG DANH SÁCH NHÂN VIÊN + TÌM KIẾM + BỘ LỌC
# =========================================================
@nhan_vien_bp.route('/nhan-vien', methods=['GET'])
def danh_sach():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    # Lấy các tham số lọc từ URL (Query String)
    search_query = request.args.get('search', '').strip()
    chuc_vu_filter = request.args.get('chuc_vu', 'Tất cả')
    
    # Lấy danh sách trạng thái được tick từ checklist (Mặc định nếu trống là lấy tất cả)
    trang_thai_filters = request.args.getlist('trang_thai') 
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Sử dụng LEFT JOIN để lấy dữ liệu song song từ cả 2 bảng NhanVien và TaiKhoan
    sql = """
        SELECT nv.*, tk.ChucVu, tk.TinhTrang 
        FROM NhanVien nv
        LEFT JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien
        WHERE 1=1
    """
    params = []
    
    # Xử lý ô tìm kiếm (Tìm theo mã hoặc họ tên)
    if search_query:
        sql += " AND (nv.MaNhanVien LIKE %s OR nv.HoTen LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
        
    # Xử lý bộ lọc chức vụ nhanh
    if chuc_vu_filter != 'Tất cả':
        sql += " AND tk.ChucVu = %s"
        params.append(chuc_vu_filter)
        
    # Xử lý bộ lọc trạng thái tài khoản qua Checklist đổ xuống
    if trang_thai_filters and 'Tất cả' not in trang_thai_filters:
        # Chuyển đổi chuỗi text sang dạng số tương ứng trong DB (Hoạt động = 1, Khóa = 0)
        status_vals = []
        for st in trang_thai_filters:
            if st == 'Hoạt động': status_vals.append(1)
            elif st == 'Bị khóa': status_vals.append(0)
            
        if status_vals:
            format_strings = ', '.join(['%s'] * len(status_vals))
            sql += f" AND tk.TinhTrang IN ({format_strings})"
            params.extend(status_vals)

    cursor.execute(sql, tuple(params))
    ds_nhan_vien = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'pages/nhan-vien/nhan-vien.html', 
        nhan_vien=ds_nhan_vien, 
        search_query=search_query,
        current_chuc_vu=chuc_vu_filter,
        current_trang_thai=trang_thai_filters
    )

# =========================================================
# 2. ĐIỀU HƯỚNG FORM (DÙNG CHUNG CHO CẢ XEM, THÊM VÀ SỬA)
# =========================================================
@nhan_vien_bp.route('/nhan-vien/form', methods=['GET'])
def form_nhan_vien():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    action = request.args.get('action', 'add') # Các hành động: add, view, edit
    ma_nv = request.args.get('id', '')
    
    data = None
    if action in ['view', 'edit'] and ma_nv:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT nv.*, tk.TenDangNhap, tk.MatKhau, tk.ChucVu, tk.TinhTrang 
            FROM NhanVien nv
            LEFT JOIN TaiKhoan tk ON nv.MaNhanVien = tk.MaNhanVien
            WHERE nv.MaNhanVien = %s
        """, (ma_nv,))
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        
    return render_template('pages/nhan-vien/them-nhan-vien.html', action=action, data=data)

# =========================================================
# 3. XỬ LÝ LƯU DỮ LIỆU (THÊM MỚI HOẶC CẬP NHẬT BIẾN ĐỔI)
# =========================================================
@nhan_vien_bp.route('/nhan-vien/save', methods=['POST'])
def save_nhan_vien():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Kiểm tra quyền quản lý
    if session.get('role') != 'Quản lý':
        flash('Bạn không có quyền thực hiện thao tác này!')
        return redirect(url_for('nhan_vien.danh_sach'))
        
    action = request.form.get('action')
    
    # Thu thập dữ liệu từ các thẻ input name tương ứng
    ho_ten = request.form.get('ho_ten', '').strip()
    ngay_sinh = request.form.get('ngay_sinh')
    gioi_tinh = request.form.get('gioi_tinh')
    email = request.form.get('email', '').strip()
    sdt = request.form.get('sdt', '').strip()
    chuc_vu = request.form.get('chuc_vu')
    dia_chi = request.form.get('dia_chi', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    # Kiểm tra các thông tin bắt buộc nhập (Chỉ bắt buộc password khi thêm mới 'add')
    if action == 'add':
        if not all([ho_ten, ngay_sinh, gioi_tinh, email, sdt, chuc_vu, username, password]):
            flash('Vui lòng điền đầy đủ các thông tin bắt buộc có dấu (*) !')
            return redirect(request.referrer)
    else: # Trường hợp edit không bắt buộc nhập password mới
        if not all([ho_ten, ngay_sinh, gioi_tinh, email, sdt, chuc_vu, username]):
            flash('Vui lòng điền đầy đủ các thông tin bắt buộc có dấu (*) !')
            return redirect(request.referrer)
    
    # 1. VALIDATION NGHIỆP VỤ
    if not (10 <= len(ho_ten) <= 35):
        flash('Họ tên phải từ 10 đến 35 ký tự.')
        return redirect(request.referrer)
    
    nam_sinh = int(ngay_sinh.split('-')[0])
    tuoi = date.today().year - nam_sinh
    if not (20 <= tuoi <= 60):
        flash('Năm sinh không hợp lệ (Tuổi phải từ 20 đến 60).')
        return redirect(request.referrer)
    
    # 2. XỬ LÝ MẬT KHẨU KHÍ HÓA HASHED
    if password: 
        hashed_pw = generate_password_hash(password)
    else:
        hashed_pw = None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if action == 'add':
            # Tìm mã lớn nhất hiện tại để tự động sinh mã nhân viên kế tiếp
            cursor.execute("SELECT MaNhanVien FROM NhanVien ORDER BY MaNhanVien DESC LIMIT 1")
            last_nv = cursor.fetchone()
            if last_nv:
                num = int(last_nv[0][2:]) + 1
                new_ma_nv = f"NV{num:02d}"
            else:
                new_ma_nv = "NV01"

            # Thực thi thêm dữ liệu vào bảng NhanVien
            cursor.execute("""
                INSERT INTO NhanVien (MaNhanVien, HoTen, GioiTinh, NgaySinh, Email, DiaChi, SoDienThoai)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (new_ma_nv, ho_ten, gioi_tinh, ngay_sinh, email, dia_chi, sdt))

            # Thực thi thêm tài khoản đồng bộ đi kèm với mật khẩu đã mã hóa (Mặc định tình trạng = 1)
            cursor.execute("""
                INSERT INTO TaiKhoan (MaNhanVien, TenDangNhap, MatKhau, ChucVu, TinhTrang)
                VALUES (%s, %s, %s, %s, 1)
            """, (new_ma_nv, username, hashed_pw, chuc_vu))
            
            flash(f'Thêm mới nhân viên {new_ma_nv} thành công!')

        elif action == 'edit':
            ma_nv = request.form.get('ma_nv')
            
            # Cập nhật thông tin bảng NhanVien
            cursor.execute("""
                UPDATE NhanVien 
                SET HoTen=%s, GioiTinh=%s, NgaySinh=%s, Email=%s, DiaChi=%s, SoDienThoai=%s
                WHERE MaNhanVien=%s
            """, (ho_ten, gioi_tinh, ngay_sinh, email, dia_chi, sdt, ma_nv))

            # Cập nhật thông tin bảng TaiKhoan dựa theo việc có thay đổi mật khẩu hay không
            if hashed_pw:
                cursor.execute("""
                    UPDATE TaiKhoan 
                    SET TenDangNhap=%s, MatKhau=%s, ChucVu=%s 
                    WHERE MaNhanVien=%s
                """, (username, hashed_pw, chuc_vu, ma_nv))
            else:
                cursor.execute("""
                    UPDATE TaiKhoan 
                    SET TenDangNhap=%s, ChucVu=%s 
                    WHERE MaNhanVien=%s
                """, (username, chuc_vu, ma_nv))
                
            flash(f'Cập nhật thông tin nhân viên {ma_nv} thành công!')

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'Có lỗi xảy ra trong quá trình cập nhật cơ sở dữ liệu: {e}')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('nhan_vien.danh_sach'))

# =========================================================
# 4. TÁC VỤ XÓA NHÂN VIÊN
# =========================================================
@nhan_vien_bp.route('/nhan-vien/xoa/<string:id>', methods=['GET'])
def xoa_nhan_vien(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Vì có ràng buộc khóa ngoại nên phải xóa bảng con TaiKhoan trước
        cursor.execute("DELETE FROM TaiKhoan WHERE MaNhanVien = %s", (id,))
        # Sau đó xóa bảng cha NhanVien
        cursor.execute("DELETE FROM NhanVien WHERE MaNhanVien = %s", (id,))
        conn.commit()
        flash(f'Đã xóa nhân viên {id} khỏi hệ thống thành công.')
    except Exception as e:
        conn.rollback()
        flash(f'Không thể xóa nhân viên này do có ràng buộc dữ liệu lịch làm việc/lịch hẹn: {e}')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('nhan_vien.danh_sach'))