import db
import instagrapi
from datetime import datetime 
import os
import urllib
import shutil
import random

CL_USERNAME = db.config["cl_username"]
CL_PASSWORD = db.config["cl_password"]
CL_SESSION_PATH = db.config["cl_session_path"]
MEDIA_PATH = db.config["media_path"]

# saving settings
### todo: include this in settings table per user
media_saving_enabled = True
saving_dont_show_again_enabled = True
saving_videos_enabled = True # not integrated anywhere yet

cl=instagrapi.Client()
### add: exception handling when no sessions exists yet
cl.set_settings(cl.load_settings(CL_SESSION_PATH))
#cl.login(CL_USERNAME,CL_PASSWORD)
#cl.delay_range = [1,5] # can set delay range our timeout to client https://github.com/adw0rd/instagrapi/issues/1311
cl.dump_settings(CL_SESSION_PATH)

db.ACTIVE_COLL_ACC_PK = db.config["active_coll_acc_pk"]
### add: exception handling when ACTIVE_COLL_ACC_PK not yet scraped yet
### db.ACTIVE_COLL_ACC_PK = cl.user_id_from_username(db.ACTIVE_COLL_ACC_STR)
### add: write to config.json


### add: account for event: unfollowing user; delete from user table and all associated media
### add: conditional: only login, if not logged in from session already
### add: include scraping of users_urls
def get_followee_list():
    """currently doesnt account for event: unfollowed user / synch with db"""
    print(str(datetime.now())+": "+"function get_followee_list started")
    info=cl.user_info(db.ACTIVE_COLL_ACC_PK)
    info_dict=info.dict()
    followee_count=info_dict["following_count"]
    if followee_count > db.unique_user_count():
        print(str(datetime.now())+": "+"more accounts followed than in db; updating user table")
        cl.login(CL_USERNAME,CL_PASSWORD)
        fl_list=cl.user_following(db.ACTIVE_COLL_ACC_PK,0) 
        for i in fl_list:
            i_dict=fl_list[i].dict()
            user_pk=i_dict["pk"]
            user_name=i_dict["username"]
            if i_dict["is_private"] is True:
                is_private = 1
            else: 
                is_private = 0
            db.c.execute("""
            INSERT OR IGNORE INTO user 
            (user_pk,user_name,is_private)
            VALUES (?,?,?)
            ;""",[user_pk,user_name,is_private])
            db.c.execute("""
            INSERT OR IGNORE INTO accounts_users
            (collector_account_pk,user_pk)
            VALUES (?,?)
                         """,[db.ACTIVE_COLL_ACC_PK,user_pk])
            db.conn.commit()
        print(str(datetime.now())+": followee_list updated")
    else:
        print(str(datetime.now())+": not more accounts followed than in db")
    db.set_last_time_followee_list_updated(db.ACTIVE_COLL_ACC_PK)
    print(str(datetime.now())+": function get_followee_list finished")

class media:
    def __init__(
            self,
            media_pk,
            media_id,
            media_code,
            media_type,
            user_pk,
            user_name,
            caption_text,
            is_favorite,
            dont_show_again,
            last_shown,
            collector_account_pk,
            position_in_album,
            parent_pk):
        self.media_pk = media_pk
        self.media_id = media_id
        self.media_code = media_code
        self.media_type = media_type
        self.user_pk = user_pk
        self.user_name = user_name
        self.caption_text = caption_text
        self.is_favorite = is_favorite
        self.dont_show_again = dont_show_again
        self.last_shown = last_shown
        self.collector_account_pk = collector_account_pk
        self.position_in_album = position_in_album
        self.parent_pk = parent_pk

        self.media_path = str(MEDIA_PATH)+str(db.ACTIVE_COLL_ACC_PK)+"/"

    def load_file(self):
        """
        - quite large function to avoid extra instagram API requests
        - checking for file existance not handled through db or permanent object variable to allow for manual file deletion; would enable mismatch of records
        """
        print(str(datetime.now())+": function load_file started")
        # check if in media storage; if yes: copy over to work file
        if self.media_type == 1:
            self.suffix = ".jpg"
            media_type_str = "image"
            dict_str = "thumbnail_url"
        else: # media_type == 2
            self.suffix = ".mp4"
            media_type_str = "video"
            dict_str = "video_url"
        
        self.file_path = str(MEDIA_PATH)+str(db.ACTIVE_COLL_ACC_PK)+"/"+str(self.media_pk)+str(self.suffix)
        work_file = "work_file"+str(self.suffix)
        print("query path is: "+str(self.file_path))
        if os.path.exists(self.file_path):
            print(str(datetime.now())+": "+str(self.media_pk)+" / "+str(media_type_str)+" exists in media storage")
            shutil.copy(self.file_path,work_file)
            print(str(datetime.now())+": "+str(self.media_pk)+" / "+str(media_type_str)+" copied to work file")
        else:
            print(str(datetime.now())+": "+str(self.media_pk)+" / "+str(media_type_str)+" does not exist in media storage; starting getting media from instagram")

            if self.parent_pk is None:
                self.post_pk = self.media_pk
            else:
                self.post_pk = self.parent_pk

            self.post = cl.media_info(self.post_pk)
            self.post_dict = self.post.dict()
            if self.parent_pk is None:
                urllib.request.urlretrieve(self.post_dict[dict_str],work_file)
            else:
                urllib.request.urlretrieve(self.post_dict["resources"][self.position_in_album][dict_str],work_file)
            print(str(datetime.now())+": "+str(self.media_pk)+" / "+str(media_type_str)+" saved to work_file")
            
            if media_saving_enabled is True:
                shutil.copy(work_file,self.file_path)
                print(str(datetime.now())+": "+str(self.media_pk)+" copied to media storage")
            else:
                print(str(datetime.now())+": media saving not enabled; function finished")


def load_db_media_values(media_pk):
    """syntax: set asterisk * before the function to load into object"""
    result = db.c.execute(
    """SELECT m.media_pk,m.media_id,m.media_code,m.media_type,m.user_pk,u.user_name,m.caption_text,am.is_favorite,
    am.dont_show_again,am.last_shown,am.collector_account_pk,m.position_in_album,m.parent_pk 
    FROM accounts_medias AS am JOIN media AS m ON am.media_pk = m.media_pk JOIN user AS u ON m.user_pk = u.user_pk WHERE m.media_pk = (?)"""
    ,[media_pk]).fetchone()
    return result

def add_relation(post):
    def insert(media_pk):
        db.c.execute("""
                     INSERT OR IGNORE INTO accounts_medias
                     (collector_account_pk,media_pk,is_favorite,dont_show_again,last_shown)
                     VALUES (?,?,?,?,?)""",[db.ACTIVE_COLL_ACC_PK,media_pk,0,0,None])
        db.conn.commit()
    post_dict = post.dict()
    if post_dict["media_type"] == 8:
        print("is media type 8")
        for i in range(len(post_dict["resources"])):
            media_pk = int(post_dict["resources"][i]["pk"])
            insert(media_pk)
    else:
        media_pk=int(post_dict["pk"])
        insert(media_pk)
        
### add: saving media function with conditional for media_saving_enabled
def insert_media(post):
    """
    - must parse single post as argument, otherwise would need indexing
    - can use None since that equals to NULL in SQL with sqlite3 library
    """
    post_dict = post.dict()
    if post_dict["media_type"] == 8:
        print("is media type 8")
        for i in range(len(post_dict["resources"])):
            media_pk = int(post_dict["resources"][i]["pk"])
            media_id = None
            media_code = post_dict["code"] # using parent post code
            media_type = post_dict["resources"][i]["media_type"]
            user_pk = int(post_dict["user"]["pk"])
            user_name=post_dict["user"]["username"]
            caption_text = post_dict["caption_text"]
            is_favorite = 0
            dont_show_again = 0
            last_shown = None
            collector_account_pk = db.ACTIVE_COLL_ACC_PK
            position_in_album = i
            parent_pk = post_dict["pk"]
            data={"media_pk":media_pk,"media_id":media_id,"media_code":media_code,"media_type":media_type,"user_pk":user_pk,"user_name":user_name,"caption_text":caption_text,"is_favorite":is_favorite,
                  "dont_show_again":dont_show_again,"last_shown":last_shown,"collector_account_pk":collector_account_pk,"position_in_album":position_in_album,"parent_pk":parent_pk}
            db.insert_media_db(data)
            print(str(datetime.now())+": "+str(media_pk)+" saved to db")
    else: # for media_type 1 and 2
        media_pk=int(post_dict["pk"])
        media_id=post_dict["id"]
        media_code=post_dict["code"]
        media_type=post_dict["media_type"]
        user_pk=int(post_dict["user"]["pk"])
        user_name=post_dict["user"]["username"]
        caption_text = post_dict["caption_text"]
        is_favorite= 0 # set to zero per default
        dont_show_again = 0 # set to zero per default
        last_shown = None
        collector_account_pk = db.ACTIVE_COLL_ACC_PK
        position_in_album = None
        parent_pk = None
        data={"media_pk":media_pk,"media_id":media_id,"media_code":media_code,"media_type":media_type,"user_pk":user_pk,"user_name":user_name,"caption_text":caption_text,"is_favorite":is_favorite,"dont_show_again":dont_show_again,"last_shown":last_shown,"collector_account_pk":collector_account_pk,"position_in_album":position_in_album,"parent_pk":parent_pk}
        db.insert_media_db(data)
        print(str(datetime.now())+": "+str(media_pk)+" saved to db")

def loop_latest(user): 
    """loop to latest post of user"""
    print(str(datetime.now())+": function loop_latest started")
    i = 0
    while True:
        print(str(datetime.now())+": loop round "+str(i+1))
        i = i + 1
        posts = cl.user_medias_gql(user,i)
        print(posts)
        post = posts[(i-1)]
        print(post)
        if db.within_db_query(post) is True:
            if db.query_relation_exists(post) is False:
                add_relation(post)
                break
            else:
                continue
        else:
            insert_media(post)
            break
    print(str(datetime.now())+": function loop_latest finished. Looped to "+str(i)+". post.")

def get_X_from_random_user(X):
    """X must be higher than one, otherwise list post indexing wont work"""
    print(str(datetime.now())+": function get_X_from_random_user started")
    user = db.get_random_user()
    posts = cl.user_medias_gql(user,X)
    new_media_counter = 0
    for i in range(len(posts)):
        post = posts[i]
        if db.within_db_query(post) is False:
            insert_media(post)
            new_media_counter = new_media_counter + 1
        else:
            print(str(datetime.now())+": is already within db; no saving needed")
            if db.query_relation_exists(post) is False:
                add_relation(post)
            else:
                print("relation already exists")
    print(str(datetime.now())+": function get_X_from_random_user finished. "+str(new_media_counter)+" media saved to db")

def get_X_from_all_users(X):
    """X must be higher than one, otherwise list post indexing wont work"""
    print(str(datetime.now())+": function get_x_from_all_users started")
    db.c.execute("SELECT user_pk FROM user;")
    db.conn.commit()
    results=db.c.fetchall()
    list = []
    for i in results:
        list.append(i[0])
    random.shuffle(list) # in order to not always getting the first positions in the list, when limiting media amount
    new_posts_counter = 0
    posts_limit_counter = 0
    for i in list:
        posts = cl.user_medias_gql(i,X)
        for i in range(len(posts)):
            post = posts[i]
            if db.within_db_query(post) is False:
                insert_media(post)
                new_posts_counter = new_posts_counter + 1
                posts_limit_counter = posts_limit_counter + 1
            else:
                posts_limit_counter = posts_limit_counter + 1
                print(str(datetime.now())+": is already within db; no saving needed")
                if db.query_relation_exists(post) is False:
                    add_relation(post)
                else:
                    print("relation already exists")
            print(posts_limit_counter)
    print(str(datetime.now())+": function get_x_from_all_users finished. "+str(new_posts_counter)+" media saved to db")