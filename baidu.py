from aip import AipOcr
from PIL import Image, ImageDraw, ImageFont 
import numpy as np 
import cv2 
APP_ID = '8222257'
API_KEY = 'YGMghwNb5VMfA5GAMC8NRY5E' 
SECRET_KEY = 'LgzjKj75E3TlcjCwpXEEwrT1P2yboSc4' 
client = AipOcr(APP_ID, API_KEY, SECRET_KEY) 
client.setConnectionTimeoutInMillis(5000) 
client.setSocketTimeoutInMillis(5000) 
def cv2ImgAddText(img, text, left, top, textColor, textSize): 
    if (isinstance(img, np.ndarray)): 
        img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) 
    draw = ImageDraw.Draw(img) 
    fontStyle = ImageFont.truetype("simsun.ttc", textSize, encoding="utf-8") 
    draw.text((left, top), text, textColor, font=fontStyle) 
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
def getFileContent(filePath): 
    with open(filePath, 'rb') as fp: 
        return fp.read() 
def license_recognition_image(image_path): 
    image_content = getFileContent(image_path) 
    res = client.licensePlate(image_content) 
    car_number = res['words_result']['number'] 
    car_color = res['words_result']['color'] 
    code_image_list = [] 
    if res is not None: 
        print('车牌号码:' + car_number) 
        print('车牌颜色:' + car_color) 
        location = res['words_result']['vertexes_location'] 
        start_x = location[0]['x'] 
        start_y = location[0]['y'] 
        end_x = location[2]['x'] 
        end_y = location[2]['y'] 
        img = cv2.imread(image_path) 
        cv2.rectangle(img, (start_x, start_y), (end_x, end_y), (0, 0, 255), 5) 
        txt = car_number + ' ' + car_color 
        img_txt = cv2ImgAddText(img, txt, start_x, start_y - 30, (0, 255, 0), 30) 
        code_image_list.append((car_number, img_txt)) 
    else:
        print('车牌识别失败!') 
    return code_image_list 
if __name__ == '__main__': 
    imgPath = 'frame.jpg' 
    code_image_list = license_recognition_image(imgPath) 
    print(code_image_list[0][0]) 
    cv2.imshow('img', code_image_list[0][1]) 
    cv2.waitKey(0) 
    cv2.destroyAllWindows()