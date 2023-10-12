import sqlalchemy as sqa
import sqlalchemy_utils as sqau
import os
from datetime import datetime
import time
import tempfile
import shutil
import tensorflow as tf
import db
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Dense, Flatten
from tensorflow.keras.models import load_model


# set fixed training variables
TOTAL_BATCH_SIZE = 40
TRAIN_PERCENTAGE = 0.9 # including validation portion
VAL_PERCENTAGE = 1/9 # within train portion
MODEL_PATH = db.config["ml_model_path"] 
ACTIVE_MEDIA_PATH = db.config["media_path"]+db.ACTIVE_COLL_ACC_PK+"/"


### can be moved from db.py-file when sqlalchemy fully integrated
def db_setup():
    CONN_STR="sqlite:///"+db.DB_PATH
    if os.path.isfile(db.DB_PATH):
        print(str(datetime.now())+": db file exists, creating connection")
        pass
    else:
        print(str(datetime.now())+": db file does not exist, creating new db")
        sqau.create_database(CONN_STR)
    global engine
    engine = sqa.create_engine(CONN_STR) #,echo=True) # only enalbe for debugging
    global conn
    conn = engine.connect()
    global metadata_db
    metadata_db = sqa.MetaData()
    metadata_db.reflect(bind=conn)

db_setup()

### loading all necessary tables into sqlalchemy here; later move this part to db file
accounts_medias = sqa.Table("accounts_medias",metadata_db,autoload=True)
media = sqa.Table("media",metadata_db,autoload=True)
####

def create_ml_model():
    global model
    model = Sequential()
    model.add(Conv2D(16, (3,3), 1, activation='relu', input_shape=(256,256,3)))
    model.add(MaxPooling2D())
    model.add(Conv2D(32, (3,3), 1, activation='relu'))
    model.add(MaxPooling2D())
    model.add(Conv2D(16, (3,3), 1, activation='relu'))
    model.add(MaxPooling2D())
    model.add(Flatten())
    model.add(Dense(256, activation='relu'))
    model.add(Dense(1, activation='sigmoid'))
    model.compile('adam', loss=tf.losses.BinaryCrossentropy(), metrics=['accuracy'])
    model.save(MODEL_PATH)

def criteria_1():
    criteria_1 = conn.execute(sqa.select(sqa.func.count())
        .select_from(
            sqa.join(
                accounts_medias,
                media,
                accounts_medias.c.media_pk == media.c.media_pk,
            )
        )
        .where(accounts_medias.c.last_shown.isnot(None))
        .where(accounts_medias.c.dont_show_again == 1)
        .where(accounts_medias.c.ml_train_skipped == 0)
        .where(accounts_medias.c.ml_train_time.is_(None))
        .where(media.c.media_type == 1)
    ).scalar()
    return criteria_1

def criteria_2():
    criteria_2 = conn.execute(sqa.select(sqa.func.count())
        .select_from(
            sqa.join(
                accounts_medias,
                media,
                accounts_medias.c.media_pk == media.c.media_pk,
            )
        )
        .where(accounts_medias.c.last_shown.isnot(None))
        .where(accounts_medias.c.dont_show_again == 0)
        .where(accounts_medias.c.ml_train_skipped == 0)
        .where(accounts_medias.c.ml_train_time.is_(None))
        .where(media.c.media_type == 1)
    ).scalar()
    return criteria_2


# checking if enough media with given criterias where shown by app user in order to qualify as a training batch
def check_criterias():
    if criteria_1() >= TOTAL_BATCH_SIZE/2 and criteria_2() >= TOTAL_BATCH_SIZE/2:
            print(str(datetime.now())+": ml training criterias fulfilled")
            print(str(datetime.now())+": "+str(criteria_1())+" dont_show media and "+str(criteria_2())+" show media not used for training")
            return True
    else:
        print(str(datetime.now())+": ml training criterias not fulfilled")
        return False

def train_model():
    print(str(datetime.now())+": ml training function started")
    # load model or create new one if doesn't exists
    try:
        model = load_model(MODEL_PATH)
    except OSError:
        create_ml_model()

    temp_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(temp_dir,"show"))
    temp_show = os.path.join(temp_dir,"show")
    os.makedirs(os.path.join(temp_dir,"dont_show"))
    temp_dont_show = os.path.join(temp_dir,"dont_show")

    # getting the media_pks within criterias & were shown chronologically latest
    pks_show = conn.execute(sqa.select(accounts_medias.c.media_pk)
        .select_from(
            sqa.join(
                accounts_medias,
                media,
                accounts_medias.c.media_pk == media.c.media_pk,
            )
        )
        .where(accounts_medias.c.last_shown.isnot(None))
        .where(accounts_medias.c.dont_show_again == 0)
        .where(accounts_medias.c.ml_train_skipped == 0)
        .where(accounts_medias.c.ml_train_time.is_(None))
        .where(media.c.media_type == 1)  
        .order_by(accounts_medias.c.last_shown.asc())
        .limit(TOTAL_BATCH_SIZE/2)).scalars().all()

    pks_dont_show = conn.execute(sqa.select(accounts_medias.c.media_pk)
        .select_from(
            sqa.join(
                accounts_medias,
                media,
                accounts_medias.c.media_pk == media.c.media_pk,
            )
        )
        .where(accounts_medias.c.last_shown.isnot(None))
        .where(accounts_medias.c.dont_show_again == 1)
        .where(accounts_medias.c.ml_train_skipped == 0)
        .where(accounts_medias.c.ml_train_time.is_(None))
        .where(media.c.media_type == 1)
        .order_by(accounts_medias.c.last_shown.asc())
        .limit(TOTAL_BATCH_SIZE/2)).scalars().all()

    # creating data splits
    ### hard-coded for now
    ### use dynamic method utilizing training_data_size variable
    ### eg. with numpy slit function
    pks_show_train = pks_show[:18]
    pks_show_test = pks_show[18:21]
    pks_dont_show_train = pks_dont_show[:18]
    pks_dont_show_test = pks_dont_show[18:21]
    pks_train = pks_show_train + pks_dont_show_train
    pks_test = pks_show_test + pks_dont_show_test


    ### need to add: if file doesn't exist, load through instagrapi and save to temp dir
    for media_pk in pks_show_train:
        file_name=str(media_pk)+".jpg"
        file_path = str(ACTIVE_MEDIA_PATH)+file_name
        if os.path.isfile(file_path):
            try:
                shutil.copy2(file_path,os.path.join(temp_show,file_name))
            except OSError:
                pass
        else:
            pass

    ### need to add: if file doesnt exist, load through instagrapi and save to temp dir
    for media_pk in pks_dont_show_train:
        file_name=str(media_pk)+".jpg"
        file_path = str(ACTIVE_MEDIA_PATH)+file_name
        if os.path.isfile(file_path):
            try:
                shutil.copy2(file_path,os.path.join(temp_dont_show,file_name))
            except OSError:
                pass
        else:
            pass

    if len(os.listdir(temp_show)) == len(pks_show_train) and len(os.listdir(temp_dont_show)) == len(pks_dont_show_train):
        print("copying to temp_dir successful")
    else:
        print("copying to temp_dir not successful")

    data = tf.keras.utils.image_dataset_from_directory(
        directory=temp_dir,
        labels="inferred",
        label_mode="binary", 
        class_names=("show","dont_show"), # so that show equals 0 and dont_show equals 1
        image_size=(256, 256),
        batch_size=int(TOTAL_BATCH_SIZE*TRAIN_PERCENTAGE),  
        validation_split=VAL_PERCENTAGE,  
        subset="training",  
        seed=42)
    data = data.map(lambda x, y: (x / 255.0, y))

    hist = model.fit(data,epochs=20)

    # only logging training to db for both train and test set when training successful, otherwise skewing available distribution
    for media_pk in pks_test:
        conn.execute(accounts_medias.update().
                        where(accounts_medias.c.media_pk==media_pk,accounts_medias.c.collector_account_pk==db.ACTIVE_COLL_ACC_PK)
                        .values(ml_split_type=2,ml_train_time=int(time.time())))
        conn.commit()

    for media_pk in pks_train:
        conn.execute(accounts_medias.update().
                        where(accounts_medias.c.media_pk==media_pk,accounts_medias.c.collector_account_pk==db.ACTIVE_COLL_ACC_PK)
                        .values(ml_split_type=1,ml_train_time=int(time.time())))
        conn.commit()



    model.save(MODEL_PATH)

    ### fix: only deletes the files but not the folder
    shutil.rmtree(temp_dir)

    print(str(datetime.now())+": ml training function finished: currently "+str(criteria_1())+" dont_show media and "+str(criteria_2())+" show media remaining")

def full_training():
    while check_criterias() is True:
        train_model()
    