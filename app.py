import os
from flask import Flask, jsonify, request, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.exc import NoResultFound
from ultralytics import YOLO
import exifread
import time
import cv2
from dotenv import load_dotenv
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
load_dotenv()
WORHBENCH_PASSWORD = os.getenv('WORHBENCH_PASSWORD')
# WORHBENCH_PASSWORD = os.environ.get('WORHBENCH_PASSWORD')
print(WORHBENCH_PASSWORD)
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{WORHBENCH_PASSWORD}@localhost:3306/bird-identification'

# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/bird-identification'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bird_name_table = {
    "Columba livia (Rock_Pigeon)": "野鴿",
    "Carpodacus formosanus": "台灣朱雀",
    "Syrmaticus mikado": "帝雉",
    "Lophura swinhoii": "藍腹鵰",
    "Urocissa caerulea": "台灣藍鵲",
    "Alpine Accentor": "岩鷚",
    "Gorsachius melanolophus": "黑冠麻鷺",
    "Gracupica nigricollis": "黑領椋鳥",
    "Passer cinnamomeus": "山麻雀",
    "Passer montanus": "麻雀",
    "Lanius cristatus": "紅尾伯勞",
    "Actinodura morrisoniana": "紋翼畫眉",
    "Pterorhinus ruficeps": "臺灣白喉噪眉",
    "Acridotheres javanicus": "白尾八哥",
    "Acridotheres tristis": "家八哥",
    "Acridotheres cristatellus": "冠八哥",
    "Phasianus colchicus": "環頸雉",
    "Periparus ater(Coal Tit)": "煤山雀",
    "Aplonis panayensis": "亞洲輝椋鳥",
    "Copsychus malabaricus": "白腰鵲鴝",
    "Sturnia malabarica": "灰頭椋鳥"
}

class Users(db.Model):
    _id = db.Column('id', db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)

    def __init__(self, username, password):
        self.username = username
        self.password = password

class IdentificationRecords(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.String(100))
    bird_names = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    image_filenames = db.Column(db.String(255), nullable=False)
    observation_date = db.Column(db.String(100))

@app.route('/POST/register', methods=['POST'])
def register():
    data = request.get_json()
    new_user = Users(username=data['username'], password=data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/POST/login', methods=['POST'])
def login():
    data = request.get_json()
    user = Users.query.filter_by(username=data['username']).first()
    if user and user.password == data['password']:
        return jsonify({'message': 'Login successful', 'username': data['username']}), 201
    else:
        return jsonify({'message': 'Invalid username or password'}), 401

@app.route('/GET/static/images/<path:image_name>')
def get_image(image_name):
    return send_from_directory('static/images', image_name)

@app.route('/GET/all_users')
def get_all_users():
    users = Users.query.all()
    user_list = []
    for user in users:
        user_data = {
            'id': user._id,
            'username': user.username,
            'password': user.password
        }
        user_list.append(user_data)
    return jsonify(user_list), 200

@app.route('/SELECT/user_identification_record', methods=['POST'])
def get_user_identification_record():
    data = request.get_json()
    username = data['username']
    user = Users.query.filter_by(username=username).first()
    if user:
        identification_records = IdentificationRecords.query.filter_by(user_id=user._id).all()
        records_list = []
        for record in identification_records:
            image_filenames = []
            for image_filename in record.image_filenames.split(','):
                image_filename = image_filename.strip()
                if image_filename:
                    image_filenames.append(url_for('get_image', image_name=image_filename))

            record_data = {
                'bird_names': record.bird_names,
                'latitude': record.latitude,
                'longitude': record.longitude,
                'image_filenames': image_filenames,  
                'observation_date': record.observation_date
            }
            records_list.append(record_data)
        return jsonify(records_list), 201
    else:
        return jsonify({'message': 'User not found'}), 404

@app.route('/SELECT/user_identification_record_by_timestamp', methods=['POST'])
def get_single_user_identification_record():
    data = request.get_json()
    username = data['username']
    timestamp = data['timestamp']

    user = Users.query.filter_by(username=username).first()
    if user:
        identification_record = IdentificationRecords.query.filter_by(user_id=user._id, timestamp=timestamp).first()
        if identification_record:
            image_filenames = []
            bird_names = []
            for image_filename in identification_record.image_filenames.split(','):
                image_filename = image_filename.strip()
                if image_filename:
                    image_filenames.append(url_for('get_image', image_name=image_filename))

            bird_names = identification_record.bird_names.split(",")
            record_data = {
                'bird_names': bird_names,
                'latitude': identification_record.latitude,
                'longitude': identification_record.longitude,
                'image_filenames': image_filenames,
                'observation_date': identification_record.observation_date
            }
            return jsonify(record_data), 201
        else:
            return jsonify({'message': 'Record not found'}), 404
    else:
        return jsonify({'message': 'User not found'}), 404

@app.route('/POST/identify_image', methods=['POST'])
def identify_image():
    username = request.form['username']
    image = request.files['file']
    user_id = get_user_id(username)
    print(image)

    timestamp = str(int(time.time()))
    filepath = f"static/images/{username}_{timestamp}.jpg"
    image.save(filepath)

    model = YOLO("model/best.pt")
    results = model.predict(
        source = filepath,
        conf = 0.7,
        save = True,
        save_txt = True,
        save_conf = True,
        save_crop = True,
        visualize = False,
    )
    latitude, longitude, datetime_original = get_image_info(results[0].path)

    predict_dir = results[0].save_dir
    name_list, image_filenames_list =  out_cutting_image(results[0].names ,predict_dir)
    if name_list == []:
        return jsonify({'message': 'No bird detected in the image'}), 400

    image_filenames_str = ','.join(image_filenames_list)
    name_str = ','.join(name_list)

    add_identification_record(user_id, timestamp, name_str, latitude, longitude, image_filenames_str, datetime_original)
    
    return jsonify({'message': 'Identify image base64 processed successfully','timestamp': timestamp}), 201



def add_identification_record(_user_id, _timestamp, _name_list, _latitude, _longitude, _image_filenames_list, _datetime):
    new_record = IdentificationRecords(
        user_id=_user_id,
        timestamp=_timestamp,
        bird_names=_name_list,
        latitude=_latitude,
        longitude=_longitude,
        image_filenames=_image_filenames_list,
        observation_date=_datetime
    )
    db.session.add(new_record)
    db.session.commit()
    
def get_image_info(image_path):
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f, details=False)
        
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
            gps_latitude_tag = tags.get('GPS GPSLatitude')
            gps_longitude_tag = tags.get('GPS GPSLongitude')
            
            gps_latitude_str = str(gps_latitude_tag.values).strip("[]")
            gps_longitude_str = str(gps_longitude_tag.values).strip("[]")

            gps_latitude = dms_to_dd(gps_latitude_str)
            gps_longitude = dms_to_dd(gps_longitude_str)

        else:
            gps_latitude, gps_longitude = None, None
        from datetime import datetime
        if 'Image DateTime' in tags:
            image_datetime = tags.get('Image DateTime')
            image_datetime_str = str(image_datetime).split('=')[-1].split('@')[0].strip()
            image_datetime_obj = datetime.strptime(image_datetime_str, "%Y:%m:%d %H:%M:%S")
            formatted_datetime_str = image_datetime_obj.strftime("%Y/%m/%d %H:%M:%S")
        else:
            formatted_datetime_str = None
        
        return gps_latitude, gps_longitude, formatted_datetime_str

def dms_to_dd(dms_str):
    dms_parts = dms_str.split(',')
    degrees = float(dms_parts[0])
    minutes = float(dms_parts[1])
    seconds_fraction = float(dms_parts[2].split('/')[0]) / float(dms_parts[2].split('/')[1])
    return degrees + minutes / 60 + seconds_fraction / 3600

def get_user_id(username):
    try:
        user = Users.query.filter_by(username=username).one()
        return user._id
    except NoResultFound:
        return None

def out_cutting_image(class_name, predict_dir):
    image_file = [f for f in os.listdir(predict_dir) if f.endswith('.jpg')]
    image = cv2.imread(os.path.join(predict_dir, image_file[0]))

    labels_dir = os.path.join(predict_dir, 'labels')
    label_file = [f for f in os.listdir(labels_dir) if f.endswith('.txt')]
    if label_file == []:
        return [], []
    
    with open(os.path.join(labels_dir, label_file[0]), 'r') as f:
        lines = f.readlines()

        name_list = []
        image_path_list = []
        for idx, line in enumerate(lines):
            parts = line.split()
            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])

            # 將相對於圖像尺寸的標記轉換為絕對座標
            image_height, image_width, _ = image.shape
            x_center *= image_width
            y_center *= image_height
            width *= image_width
            height *= image_height

            # 計算左上角和右下角座標
            x_min = int(x_center - width / 2)
            y_min = int(y_center - height / 2)
            x_max = int(x_center + width / 2)
            y_max = int(y_center + height / 2)

            # 切割圖像區域
            cropped_image = image[y_min:y_max, x_min:x_max]

            # 將切割的圖像儲存為新的檔案
            target_filename = f"cutting_{idx}_{label_file[0].replace('.txt', '.jpg')}"
            target_filepath = os.path.join(f"static/images",target_filename)

            # 保存切割後的圖像
            cv2.imwrite(target_filepath, cropped_image)
            print(f"已切割並保存: {target_filepath}")

            # 將類別名稱添加到類別列表中
            name_list.append(bird_name_table[class_name[class_id]])

            # 將圖像路徑添加到圖像路徑列表中
            image_path_list.append(target_filename)
    print("所有圖像切割完成")
    return name_list, image_path_list


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0',port=5001)