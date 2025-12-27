import cv2
import warnings
import numpy as np
from PIL import ImageFont
from PIL import Image
from PIL import ImageDraw
import hyperlpr3 as lpr3
warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="invalid value encountered in scalar divide")
catcher = lpr3.LicensePlateCatcher(detect_level=lpr3.DETECT_LEVEL_HIGH)
font_ch = ImageFont.truetype("simsun.ttc", 20, 0)
def draw_plate_on_image(img, box1, text1, font):
    x1, y1, x2, y2 = box1
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2, cv2.LINE_AA)
    data = Image.fromarray(img)
    draw = ImageDraw.Draw(data)
    draw.text((x1, y1 - 27), text1, (0, 0, 255), font=font)
    res = np.asarray(data)
    return res
def license_recognition_image(path):
    image = cv2.imread(path)
    results = catcher(image)
    code_image_list = []
    for code, confidence, type_idx, box in results:
        text = f"{code} - {confidence:.2f}"
        image = draw_plate_on_image(image, box, text, font=font_ch)
        code_image_list.append((code, image))
    return code_image_list
if __name__ == "__main__":
    file_pic = r"frame.jpg"
    code_image_list = license_recognition_image(file_pic)
    print(code_image_list[0][0])
    cv2.imshow("License Plate Recognition(Picture)", code_image_list[0][1])
    cv2.waitKey(0)
