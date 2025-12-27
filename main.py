import os
import cv2
import uuid
import numpy as np
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageDraw, ImageFont
from aip import AipOcr
import pymysql
from pymysql.cursors import DictCursor
from config import DATABASE_CONFIG, BAIDU_OCR_CONFIG, PARKING_CONFIG

# 初始化Flask应用
app = Flask(__name__)
app.secret_key = "parking_system_secret_key_2024"  # 用于session加密
app.config["UPLOAD_FOLDER"] = PARKING_CONFIG["CAPTURE_SAVE_PATH"]
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)  # 确保抓拍目录存在
app.config['MAX_CONTENT_LENGTH'] = 400 * 1024 * 1024  # 限制上传文件大小为400MB

# 允许的文件扩展名
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

# 启用CSRF保护
csrf = CSRFProtect(app)

# 初始化百度OCR客户端
baidu_ocr_client = AipOcr(
    BAIDU_OCR_CONFIG["APP_ID"],
    BAIDU_OCR_CONFIG["API_KEY"],
    BAIDU_OCR_CONFIG["SECRET_KEY"]
)
baidu_ocr_client.setConnectionTimeoutInMillis(5000)  # 连接超时
baidu_ocr_client.setSocketTimeoutInMillis(5000)  # socket超时

# 初始化Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # 未登录时跳转的页面


# -------------------------- 数据库工具函数 --------------------------
def get_db_connection():
    """获取数据库连接"""
    conn = pymysql.connect(
        host=DATABASE_CONFIG["HOST"],
        port=DATABASE_CONFIG["PORT"],
        user=DATABASE_CONFIG["USER"],
        password=DATABASE_CONFIG["PASSWORD"],
        db=DATABASE_CONFIG["DATABASE"],
        charset=DATABASE_CONFIG["CHARSET"],
        cursorclass=DictCursor
    )
    return conn


def close_db_connection(conn):
    """关闭数据库连接"""
    if conn:
        conn.close()


# -------------------------- 用户认证相关 --------------------------
class User(UserMixin):
    """Flask-Login用户类"""

    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role  # 0-普通用户，1-管理员


@login_manager.user_loader
def load_user(user_id):
    """根据用户ID加载用户（Flask-Login必需）"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, role FROM t_user WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user:
                return User(user["id"], user["username"], user["role"])
            return None
    finally:
        close_db_connection(conn)


@app.route("/login", methods=["GET", "POST"])
def login():
    """用户登录"""
    # 如果已登录，直接跳转到主页
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, role FROM t_user WHERE username = %s AND password = %s",
                    (username, password)
                )
                user = cursor.fetchone()
                if user:
                    # 登录成功，记录用户信息
                    login_user(User(user["id"], user["username"], user["role"]))
                    return redirect(url_for("index"))
                else:
                    return render_template("login.html", error="用户名或密码错误")
        finally:
            close_db_connection(conn)

    # GET请求：显示登录页面
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """用户注册（仅允许普通用户注册）"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # 验证密码一致性
        if password != confirm_password:
            return render_template("register.html", error="两次密码不一致")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 检查用户名是否已存在
                cursor.execute("SELECT id FROM t_user WHERE username = %s", (username,))
                if cursor.fetchone():
                    return render_template("register.html", error="用户名已存在")

                # 插入新用户（默认角色为普通用户：role=0）
                cursor.execute(
                    "INSERT INTO t_user (username, password, role) VALUES (%s, %s, 0)",
                    (username, password)
                )
                conn.commit()
                return redirect(url_for("login", success="注册成功，请登录"))
        except Exception as e:
            conn.rollback()
            return render_template("register.html", error=f"注册失败：{str(e)}")
        finally:
            close_db_connection(conn)

    # GET请求：显示注册页面
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    """用户登出"""
    logout_user()
    return redirect(url_for("login"))


# -------------------------- 管理员功能 --------------------------
@app.route("/admin")
@login_required
def admin_dashboard():
    """管理员后台（仅管理员可访问）"""
    if current_user.role != 1:
        return redirect(url_for("index"))  # 非管理员跳转到主页

    # 获取停车场管理数据
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 获取所有用户
            cursor.execute("SELECT id, username, role FROM t_user")
            users = cursor.fetchall()

            # 获取停车场配置
            cursor.execute("SELECT * FROM t_parking_lot")
            parking_lots = cursor.fetchall()

            # 获取今日交易记录
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "SELECT * FROM t_parking WHERE DATE(input_date) = %s",
                (today,)
            )
            today_records = cursor.fetchall()

            return render_template(
                "admin.html",
                users=users,
                parking_lots=parking_lots,
                today_records=today_records,
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
    finally:
        close_db_connection(conn)


@app.route("/add_user", methods=["POST"])
@login_required
def add_user():
    """添加新用户（仅管理员）"""
    if current_user.role != 1:
        return redirect(url_for("index"))

    username = request.form.get("username")
    password = request.form.get("password")
    role = int(request.form.get("role", 0))

    if not username or not password:
        flash("用户名和密码不能为空", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 检查用户名是否已存在
            cursor.execute("SELECT id FROM t_user WHERE username = %s", (username,))
            if cursor.fetchone():
                flash("用户名已存在", "error")
                return redirect(url_for("admin_dashboard"))

            # 插入新用户
            cursor.execute(
                "INSERT INTO t_user (username, password, role) VALUES (%s, %s, %s)",
                (username, password, role)
            )
            conn.commit()
            flash("用户添加成功", "success")
    except Exception as e:
        conn.rollback()
        flash(f"添加失败：{str(e)}", "error")
    finally:
        close_db_connection(conn)

    return redirect(url_for("admin_dashboard"))


@app.route("/delete_user/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    """删除用户（仅管理员）"""
    if current_user.role != 1:
        return jsonify({"status": "error", "message": "没有权限执行此操作"})

    # 不能删除自己
    if int(current_user.id) == user_id:
        return jsonify({"status": "error", "message": "不能删除当前登录用户"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 不能删除管理员
            cursor.execute("SELECT role FROM t_user WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user and user["role"] == 1:
                return jsonify({"status": "error", "message": "不能删除管理员用户"})

            # 执行删除
            cursor.execute("DELETE FROM t_user WHERE id = %s", (user_id,))
            conn.commit()
            return jsonify({"status": "success", "message": "用户已删除"})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        close_db_connection(conn)


@app.route("/update_parking_config", methods=["POST"])
@login_required
def update_parking_config():
    """更新停车场配置（仅管理员）"""
    if current_user.role != 1:
        return redirect(url_for("index"))

    park_id = request.form.get("park_id")
    total_lot = request.form.get("total_lot")
    unit_price = request.form.get("unit_price")

    if not park_id or not total_lot or not unit_price:
        flash("所有字段都是必填的", "error")
        return redirect(url_for("admin_dashboard"))

    try:
        total_lot = int(total_lot)
        unit_price = float(unit_price)
        if total_lot <= 0 or unit_price <= 0:
            flash("总车位数和费率必须为正数", "error")
            return redirect(url_for("admin_dashboard"))
    except ValueError:
        flash("总车位数和费率格式不正确", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 计算剩余车位 = 总车位 - 已停车数量
            cursor.execute("SELECT COUNT(*) as parked FROM t_parking WHERE park_id = %s AND status = 1", (park_id,))
            parked_count = cursor.fetchone()["parked"]
            remaining_lot = max(total_lot - parked_count, 0)

            # 更新停车场配置
            cursor.execute(
                "UPDATE t_parking_lot SET lot_num = %s, remaining_lot = %s, unit_price = %s WHERE id = %s",
                (total_lot, remaining_lot, unit_price, park_id)
            )
            conn.commit()
            flash("停车场配置更新成功", "success")
    except Exception as e:
        conn.rollback()
        flash(f"更新失败：{str(e)}", "error")
    finally:
        close_db_connection(conn)

    return redirect(url_for("admin_dashboard"))


# -------------------------- 工具函数 --------------------------
def allowed_file(filename, allowed_extensions):
    """检查文件是否为允许的类型"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


def cv2ImgAddText(img, text, left, top, textColor=(0, 255, 0), textSize=30):
    """在OpenCV图像上添加中文文字"""
    if isinstance(img, np.ndarray):
        img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    # 尝试加载多种中文字体，增加兼容性
    fonts = ["simsun.ttc", "simhei.ttf", "msyh.ttc", "microsoftyahei.ttc"]
    fontStyle = None
    for font in fonts:
        try:
            fontStyle = ImageFont.truetype(font, textSize, encoding="utf-8")
            break
        except:
            continue

    # 如果没有找到中文字体，使用默认字体（可能无法显示中文）
    if not fontStyle:
        fontStyle = ImageFont.load_default()

    draw.text((left, top), text, textColor, font=fontStyle)
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def baidu_license_recognition(image_path):
    """调用百度OCR API识别车牌"""

    # 读取图片内容
    def get_file_content(file_path):
        with open(file_path, "rb") as fp:
            return fp.read()

    image_content = get_file_content(image_path)
    try:
        # 调用百度车牌识别接口
        res = baidu_ocr_client.licensePlate(image_content)
        if "words_result" not in res:
            return None, "百度API未返回识别结果"

        # 提取车牌信息
        result = res["words_result"]
        car_number = result.get("number", "")  # 车牌号
        car_color = result.get("color", "")  # 车牌颜色
        location = result.get("vertexes_location", [])  # 车牌位置

        if not car_number or len(location) < 4:
            return None, "未识别到有效车牌信息"

        # 在图片上绘制车牌框和文字
        img = cv2.imread(image_path)
        start_x = location[0]["x"]
        start_y = location[0]["y"]
        end_x = location[2]["x"]
        end_y = location[2]["y"]
        # 绘制红色边框
        cv2.rectangle(img, (start_x, start_y), (end_x, end_y), (0, 0, 255), 5)
        # 添加车牌号和颜色文字
        txt = f"{car_number} ({car_color})"
        img_with_text = cv2ImgAddText(img, txt, start_x, start_y - 40, (0, 255, 0), 30)

        # 保存带标注的图片
        marked_image_path = image_path.replace(".jpg", "_marked.jpg")
        cv2.imwrite(marked_image_path, img_with_text)

        return {
            "car_number": car_number,
            "car_color": car_color,
            "original_image": image_path,
            "marked_image": marked_image_path
        }, None
    except Exception as e:
        return None, f"识别出错：{str(e)}"


# -------------------------- 核心业务接口 --------------------------
@app.route("/")
@login_required
def index():
    """系统主页（需登录才能访问）"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 获取停车场基础信息（剩余车位、单价）
            cursor.execute(
                "SELECT remaining_lot, unit_price FROM t_parking_lot WHERE id = %s",
                (PARKING_CONFIG["DEFAULT_PARK_ID"],)
            )
            parking_info = cursor.fetchone() or {"remaining_lot": 0, "unit_price": 3}

            # 获取当前在场车辆信息
            cursor.execute(
                "SELECT license_plate, input_date FROM t_parking "
                "WHERE park_id = %s AND status = 1 ORDER BY input_date DESC",
                (PARKING_CONFIG["DEFAULT_PARK_ID"],)
            )
            current_cars = cursor.fetchall()

            return render_template(
                "index.html",
                remaining_lot=parking_info["remaining_lot"],
                unit_price=parking_info["unit_price"],
                current_cars=current_cars,
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                current_user=current_user  # 传递当前用户信息用于权限判断
            )
    finally:
        close_db_connection(conn)


@app.route("/capture", methods=["POST"])
@login_required
def capture_image():
    """抓拍摄像头图像（支持前端视频流抓拍）"""
    try:
        # 检查是否是从前端视频流获取的图像
        data = request.get_json()
        if data and "image_data" in data:
            # 处理前端传递的base64图像数据
            image_data = data.get('image_data', '').replace('data:image/jpeg;base64,', '')
            if not image_data:
                return jsonify({"status": "error", "message": "未接收到图像数据"})

            # 解码并保存图像
            capture_time = datetime.now().strftime("%Y%m%d%H%M%S")
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], f"capture_{capture_time}.jpg")
            with open(image_path, "wb") as f:
                f.write(base64.b64decode(image_data))
        else:
            # 传统方式：调用本地摄像头抓拍
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return jsonify({"status": "error", "message": "摄像头调用失败"})

            # 生成唯一文件名（按时间戳）
            capture_time = datetime.now().strftime("%Y%m%d%H%M%S")
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], f"capture_{capture_time}.jpg")
            cv2.imwrite(image_path, frame)

        # 返回抓拍图片路径（前端用于预览）
        return jsonify({
            "status": "success",
            "image_path": url_for('static', filename=f'captures/{os.path.basename(image_path)}')
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"抓拍失败：{str(e)}"})


@app.route("/recognize", methods=["POST"])
@login_required
def recognize_license():
    """识别车牌并处理出入场逻辑"""
    image_path = request.form.get("image_path")
    if not image_path:
        return jsonify({"status": "error", "message": "图片路径无效"})

    # 构建完整的图片路径
    full_image_path = os.path.join(app.root_path, 'static', image_path.replace('/static/', ''))
    if not os.path.exists(full_image_path):
        return jsonify({"status": "error", "message": f"图片不存在: {full_image_path}"})

    # 调用百度API识别车牌
    recognition_result, error = baidu_license_recognition(full_image_path)
    if error:
        return jsonify({"status": "error", "message": error})

    car_number = recognition_result["car_number"]
    marked_image_path = recognition_result["marked_image"]
    # 生成前端可访问的带标注图片路径
    relative_marked_path = url_for('static', filename=f'captures/{os.path.basename(marked_image_path)}')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 检查车辆是否已在场（status=1）
            cursor.execute(
                "SELECT id, input_date FROM t_parking "
                "WHERE park_id = %s AND license_plate = %s AND status = 1",
                (PARKING_CONFIG["DEFAULT_PARK_ID"], car_number)
            )
            existing_car = cursor.fetchone()

            if existing_car:
                # 2. 车辆已在场：处理出场逻辑
                input_date = existing_car["input_date"]
                output_date = datetime.now()
                # 计算停车时间（小时）
                duration = (output_date - input_date).total_seconds() / 3600
                hours = int(duration) if (duration % 1) < 0.5 else int(duration) + 1
                hours = max(hours, 0)  # 避免负数

                # 获取停车单价
                cursor.execute(
                    "SELECT unit_price FROM t_parking_lot WHERE id = %s",
                    (PARKING_CONFIG["DEFAULT_PARK_ID"],)
                )
                unit_price = cursor.fetchone()["unit_price"]
                fee = hours * unit_price  # 计算停车费

                # 更新出场记录
                cursor.execute(
                    "UPDATE t_parking SET output_date = %s, fee = %s, status = 0 "
                    "WHERE id = %s",
                    (output_date, fee, existing_car["id"])
                )

                # 增加剩余车位（车辆离场）
                cursor.execute(
                    "UPDATE t_parking_lot SET remaining_lot = remaining_lot + 1 "
                    "WHERE id = %s",
                    (PARKING_CONFIG["DEFAULT_PARK_ID"],)
                )

                conn.commit()
                return jsonify({
                    "status": "success",
                    "type": "exit",
                    "car_number": car_number,
                    "input_date": input_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "output_date": output_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "fee": float(fee) if fee is not None else 0.0,  # 强制转换为数字
                    "marked_image": relative_marked_path
                })
            else:
                # 3. 车辆不在场：处理入场逻辑
                # 检查是否还有剩余车位
                cursor.execute(
                    "SELECT remaining_lot FROM t_parking_lot WHERE id = %s",
                    (PARKING_CONFIG["DEFAULT_PARK_ID"],)
                )
                parking_info = cursor.fetchone()
                if not parking_info or parking_info["remaining_lot"] <= 0:
                    return jsonify({"status": "error", "message": "停车场已满，无法入场"})

                # 记录入场信息
                input_date = datetime.now()
                cursor.execute(
                    "INSERT INTO t_parking (park_id, license_plate, input_date, status) "
                    "VALUES (%s, %s, %s, 1)",
                    (PARKING_CONFIG["DEFAULT_PARK_ID"], car_number, input_date)
                )

                # 减少剩余车位（车辆入场）
                cursor.execute(
                    "UPDATE t_parking_lot SET remaining_lot = remaining_lot - 1 "
                    "WHERE id = %s",
                    (PARKING_CONFIG["DEFAULT_PARK_ID"],)
                )

                conn.commit()
                return jsonify({
                    "status": "success",
                    "type": "enter",  # 入场
                    "car_number": car_number,
                    "input_date": input_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "marked_image": relative_marked_path
                })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"数据库操作失败：{str(e)}"})
    finally:
        close_db_connection(conn)


@app.route("/remaining_lot")
@login_required
def get_remaining_lot():
    """获取剩余车位数（用于前端定时刷新）"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT remaining_lot FROM t_parking_lot WHERE id = %s",
                (PARKING_CONFIG["DEFAULT_PARK_ID"],)
            )
            result = cursor.fetchone()
            return jsonify({
                "status": "success",
                "remaining_lot": result["remaining_lot"] if result else 0
            })
    finally:
        close_db_connection(conn)


@app.route("/current_cars")
@login_required
def get_current_cars():
    """获取当前在场车辆（用于前端定时刷新）"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT license_plate, input_date FROM t_parking "
                "WHERE park_id = %s AND status = 1 ORDER BY input_date DESC",
                (PARKING_CONFIG["DEFAULT_PARK_ID"],)
            )
            cars = cursor.fetchall()
            # 格式化时间显示
            for car in cars:
                car["input_date"] = car["input_date"].strftime("%Y-%m-%d %H:%M:%S")
            return jsonify({
                "status": "success",
                "current_cars": cars
            })
    finally:
        close_db_connection(conn)


@app.route('/upload_image', methods=['POST'])
@login_required
def upload_image():
    """处理图片上传"""
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "未找到图片文件"})

    file = request.files['image']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未选择图片"})

    if file and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
        # 生成唯一文件名
        filename = f"upload_{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # 返回图片路径
        return jsonify({
            "status": "success",
            "image_path": url_for('static', filename=f'captures/{filename}')
        })

    return jsonify({"status": "error", "message": "不支持的图片格式"})


@app.route('/upload_video', methods=['POST'])
@login_required
def upload_video():
    """处理视频上传并提取第一帧"""
    if 'video' not in request.files:
        return jsonify({"status": "error", "message": "未找到视频文件"})

    file = request.files['video']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未选择视频"})

    if file and allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
        # 保存视频
        video_filename = f"video_{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
        video_path = os.path.join(app.config["UPLOAD_FOLDER"], video_filename)
        file.save(video_path)

        # 提取第一帧作为预览
        frame_filename = f"frame_{uuid.uuid4()}.jpg"
        frame_path = os.path.join(app.config["UPLOAD_FOLDER"], frame_filename)

        try:
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(frame_path, frame)
                cap.release()

                return jsonify({
                    "status": "success",
                    "frame_path": url_for('static', filename=f'captures/{frame_filename}')
                })
            else:
                return jsonify({"status": "error", "message": "无法提取视频帧"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"视频处理错误: {str(e)}"})

    return jsonify({"status": "error", "message": "不支持的视频格式"})


if __name__ == '__main__':
    # 绑定0.0.0.0，端口指定为8080（Zeabur兼容）
    app.run(host='0.0.0.0', port=8080, debug=False)  # 生产环境关闭debug
