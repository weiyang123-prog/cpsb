# 数据库配置（config.py）
DATABASE_CONFIG = {
    "HOST": "localhost",  # 本地数据库填写localhost，远程填写IP
    "PORT": 3306,         # MySQL默认端口
    "USER": "root",       # 数据库用户名（如root）
    "PASSWORD": "123456", # 数据库密码
    "DATABASE": "plate",  # 数据库名
    "CHARSET": "utf8mb4"  # 字符集
}

# 百度OCR API配置
BAIDU_OCR_CONFIG = {
    "APP_ID": "8222257",          # 你的APP_ID
    "API_KEY": "YGMghwNb5VMfA5GAMC8NRY5E",  # 你的API_KEY
    "SECRET_KEY": "LgzjKj75E3TlcjCwpXEEwrT1P2yboSc4"  # 你的SECRET_KEY
}

# 停车场默认配置
PARKING_CONFIG = {
    "DEFAULT_PARK_ID": 1,  # 默认使用的停车场编号（对应t_parking_lot.id）
    "CAPTURE_SAVE_PATH": "static/captures/"  # 抓拍图片存储路径
}