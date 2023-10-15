import sqlite3
import time
from datetime import datetime
import json

with open('config.json', 'r') as config_file:
    config = json.load(config_file)

DB_PATH = config['db_path']
ACTIVE_COLL_ACC_STR = config['active_coll_acc_str']
ACTIVE_COLL_ACC_PK = "" # will be filled through media_handler file

# selection settings
### TODO: include this in settings table per user
media_type_selection = [1]
show_only_favorites_enabled = False
show_only_shown_before_enabled = False
show_only_not_shown_before_enabled = True

def setup_connection():
    global conn
    conn = sqlite3.connect(DB_PATH,check_same_thread=False)
    conn.set_trace_callback(print)
    # sqlite3.enable_callback_tracebacks(True) # only enable for debugging
    global c
    c = conn.cursor()

setup_connection()

### squlite does not really handle more granular datatypes, add through sqlalchemy
def init_settings_table():
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings
        (collector_account_pk INTEGER,
        collector_account_str TEXT,
        first_setup_done INTEGER DEFAULT 0,
        last_time_followee_list_updated INTEGER DEFAULT 0,
        last_time_media_scraped INTEGER DEFAULT 0)
    ;""")
    conn.commit()

def init_media_table():
    """ last_shown unit: unix time code format"""
    c.execute("""
            CREATE TABLE IF NOT EXISTS media
            (media_pk INTEGER PRIMARY KEY, 
            media_id TEXT,
            media_code TEXT,
            media_type INTEGER,
            user_pk INTEGER,
            caption_text TEXT,
            position_in_album INTEGER,
            parent_pk INTEGER,
            caption_text TEXT)
            ;""")
    conn.commit()

def init_user_table():
    c.execute("""
    CREATE TABLE IF NOT EXISTS user
    (user_pk INTEGER PRIMARY KEY UNIQUE,
    user_name TEXT,
    is_private INTEGER,
    external_url TEXT)
    ;""")
    conn.commit()

def init_accounts_users_table():
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts_users
    (collector_account_pk INTEGER,
    user_pk INTEGER,
    user_excluded INTEGER DEFAULT 0)
    ;""")
    conn.commit()

def init_accounts_medias_table():
    c.execute("""
    CREATE TABLE IF NOT EXITS accounts_medias
    collector_account_pk INTEGER,
    media_pk INTEGER,
    is_favorite INTEGER,
    dont_show_again INTEGER,
    last_shown INTEGER,
    ml_split_type INTEGER,
    ml_train_time INTEGER,
    ml_train_skipped
    ;""")

def init_all_tables():
    init_settings_table()
    init_user_table()
    init_media_table()
    init_accounts_users_table()
    init_accounts_medias_table()

def check_first_setup_done():
    result = c.execute("""
    SELECT first_setup_done 
     FROM settings 
     WHERE collector_account_pk = (?)""",[ACTIVE_COLL_ACC_PK]).fetchone()
    if result[0] == 0:
        print(str(datetime.now())+": first_setup is not done")
        return False
    else:
        print(str(datetime.now())+": first_setup is done")
        return True

def unique_user_count():
    result = c.execute
    ("""SELECT COUNT(DISTINCT user_pk) 
     FROM accounts_users 
     WHERE collector_account_pk = (?)""",[ACTIVE_COLL_ACC_PK]).fetchone()
    return int(result[0])

def insert_media_db(data):
    c.execute("""
              INSERT OR IGNORE INTO media
              (media_pk,media_id,media_code,media_type,user_pk,position_in_album,parent_pk,caption_text)
              VALUES (?,?,?,?,?,?,?,?)
              """,[data["media_pk"],data["media_id"],data["media_code"],data["media_type"],data["user_pk"],data["position_in_album"],data["parent_pk"],data["caption_text"]])
    conn.commit()
    c.execute("""INSERT OR IGNORE INTO accounts_medias
              (collector_account_pk,media_pk,is_favorite,dont_show_again,last_shown)
              VALUES (?,?,?,?,?)""",
              [data["collector_account_pk"],data["media_pk"],data["is_favorite"],data["dont_show_again"],data["last_shown"]])
    conn.commit()

def set_is_favorite_bool(bool_int,media_pk):
    c.execute("""
        UPDATE accounts_medias 
        SET is_favorite = (?)
        WHERE media_pk = (?) AND collector_account_pk = (?);
        """,[bool_int,media_pk,ACTIVE_COLL_ACC_PK])
    conn.commit()
    print(str(datetime.now())+": "+str(media_pk)+" is set to is_favorite = "+str(bool_int))

def set_dont_show_again_bool(bool_int,media_pk):
    c.execute("""
        UPDATE accounts_medias 
        SET dont_show_again = (?)
        WHERE media_pk = (?) AND collector_account_pk = (?);
        """,[bool_int,int(media_pk),ACTIVE_COLL_ACC_PK])
    conn.commit()
    print(str(datetime.now())+": "+str(media_pk)+" is set to dont_show_again = "+str(bool_int))

def set_last_shown(media_pk):
    c.execute("""
        UPDATE accounts_medias 
        SET last_shown = (?)
        WHERE media_pk = (?) AND collector_account_pk = (?);
        """,[int(time.time()),media_pk,ACTIVE_COLL_ACC_PK])
    conn.commit()
    print(str(datetime.now())+": set last_shown for "+str(media_pk)+" to "+str(int(time.time()))+" unix timestamp")

def within_db_query(post):
    post_dict = post.dict()
    pk = post_dict["pk"]
    if post_dict["media_type"] == 8:
        query = """SELECT EXISTS(SELECT 1 FROM media WHERE parent_pk = (?));"""
    else:
        query = """SELECT EXISTS(SELECT 1 FROM media WHERE media_pk = (?));"""
    c.execute(query,[pk])
    conn.commit()
    result=c.fetchone()
    if result[0] == 1:
        print(str(datetime.now())+": "+str(post_dict["pk"])+" is within db")
        return True
    else:
        print(str(datetime.now())+": "+str(post_dict["pk"])+" is not within db")
        return False

def query_relation_exists(post):
    post_dict = post.dict()
    if post_dict["media_type"] == 8:
        parent_pk = post_dict["pk"]
        result = c.execute("""
        SELECT EXISTS
        (SELECT 1 FROM media AS m JOIN accounts_medias AS am ON m.media_pk = am.media_pk 
        WHERE am.collector_account_pk = (?) AND m.parent_pk = (?) )"""
        ,[ACTIVE_COLL_ACC_PK,parent_pk]).fetchone()
    else:
        media_pk = post_dict["pk"]
        result = c.execute("""
        SELECT EXISTS
        (SELECT 1 FROM accounts_medias 
        WHERE collector_account_pk = (?) AND media_pk = (?) )"""
        ,[ACTIVE_COLL_ACC_PK,media_pk]).fetchone()
    if result[0] == 1:
        return True
    else:
        return False

def get_random_user():
    c.execute("""
    SELECT accounts_users.user_pk 
    FROM accounts_users JOIN user ON accounts_users.user_pk = user.user_pk 
    WHERE user.is_private = 0 AND accounts_users.collector_account_pk = (?) 
    AND accounts_users.user_exlcuded = 0 ORDER BY RANDOM() LIMIT 1;
    """,[ACTIVE_COLL_ACC_PK])
    conn.commit()
    return c.fetchone()[0]

### TODO: option selection through settings
### rewrite with: try 2nd query for x runs OR x seconds; 
### if it doesnt bring result, try query one
### OR go through list top 50 least viewed percentage users; go through list DESC, 
### if 1st user doesnt have qualifying media, go to second etc
def get_random_media():
    """
    absolute behemoth of if statement to allow for different "show only" variations
    always included: where dont_show_again = 0
    
    choose between option:
    - 1) get from random user
    - 2) get from random user within user group that has lowest view percentage
    - 3) get from random user within user group the has lowest absolute views
    """
    option_enabled = 1

    while True:
        if option_enabled == 1:
            user_pk = get_random_user()
        elif option_enabled == 2:
            query = """WITH not_shown AS (SELECT m.user_pk,COUNT(*) as not_shown 
            FROM media AS m JOIN accounts_medias AS am ON m.media_pk = am.media_pk 
            WHERE am.collector_account_pk = (?) AND last_shown IS NULL GROUP BY m.user_pk), 
            shown AS (SELECT m.user_pk,COUNT(*) as shown 
            FROM media AS m JOIN accounts_medias AS am ON m.media_pk = am.media_pk 
            WHERE collector_account_pk = (?) AND last_shown IS NOT NULL 
            GROUP BY m.user_pk), 
            summary AS (SELECT s.user_pk,ns.not_shown,s.shown,ns.not_shown+s.shown as sum 
            FROM shown AS s JOIN not_shown AS ns ON s.user_pk = ns.user_pk), 
            percentage_view AS (SELECT user_pk,not_shown,sum,CAST(not_shown as float)/CAST(sum as float) AS percentage 
            FROM summary ORDER BY percentage DESC LIMIT 50) SELECT user_pk FROM percentage_view ORDER BY RANDOM() LIMIT 1"""
            user_pk = c.execute(query,[ACTIVE_COLL_ACC_PK,ACTIVE_COLL_ACC_PK]).fetchone()[0]
        else:
            query = """WITH shown AS (SELECT m.user_pk,COUNT(*) as shown 
            FROM media AS m JOIN accounts_medias AS am ON m.media_pk = am.media_pk 
            WHERE collector_account_pk = (?) AND last_shown IS NOT NULL GROUP BY m.user_pk), 
            limit_selection AS (SELECT * FROM shown ORDER BY shown ASC LIMIT 50) 
            SELECT user_pk FROM limit_selection ORDER BY RANDOM() LIMIT 1"""
            user_pk = c.execute(query,[ACTIVE_COLL_ACC_PK]).fetchone()[0]
            
        if len(media_type_selection) == 2:
            media_type_string = "m.media_type IN (1,2)"
        elif 1 in media_type_selection:
            media_type_string = "m.media_type = 1"
        else: 
            media_type_string = "m.media_type = 2"

        if show_only_favorites_enabled is True:
            favorite_string = "AND am.is_favorite = 1"
            complete_string=str("""SELECT m.media_pk FROM accounts_medias AS am JOIN media AS m ON am.media_pk = m.media_pk
                                 WHERE m.user_pk = """+str(user_pk)+" AND "+str(media_type_string)+" "+str(favorite_string)+
                                 " AND am.dont_show_again = 0 ORDER BY RANDOM() LIMIT 1;")
        else:
            if show_only_shown_before_enabled is True:
                last_shown_string = "AND am.last_shown IS NOT NULL"
            elif show_only_not_shown_before_enabled is True:
                last_shown_string = "AND am.last_shown IS NULL"
            else:
                last_shown_string = ""
            complete_string=str("""SELECT m.media_pk FROM accounts_medias AS am JOIN media AS m ON am.media_pk = m.media_pk 
                                WHERE m.user_pk = """+str(user_pk)+" AND "+str(media_type_string)+" "+str(last_shown_string)+
                                " AND am.dont_show_again = 0 ORDER BY RANDOM() LIMIT 1;")
        
        try:
            result = c.execute(complete_string).fetchone()[0]
            print(str(datetime.now())+": returned media_pk is "+str(result))
            return result
        except TypeError:
            print(str(datetime.now())+": returned empty query; getting new result")
            continue

def get_last_time_followee_list_updated(collector_account_pk):
    c.execute("""
        SELECT last_time_followee_list_updated FROM settings WHERE collector_account_pk = ?;
        """,[collector_account_pk])
    conn.commit()
    result = c.fetchone()
    return result[0]

def set_last_time_followee_list_updated(collector_account_pk):
    print(str(datetime.now())+": function set_last_time_followee_list_updated started")
    c.execute("""
    UPDATE settings
    SET last_time_followee_list_updated = ?
    WHERE collector_account_pk = ?;
    """,[int(time.time()),collector_account_pk])
    conn.commit()
    print(str(datetime.now())+": function set_last_time_followee_list_updated finished")

def get_last_time_media_scraped(collector_account_pk):
    c.execute("""
        SELECT last_time_media_scraped FROM settings WHERE collector_account_pk = ?;
        """,[collector_account_pk])
    conn.commit()
    result = c.fetchone()
    return result[0]

def set_last_time_media_scraped(collector_account_pk):
    print(str(datetime.now())+": function last_time_media_scraped started")
    c.execute("""
    UPDATE settings
    SET last_time_media_scraped = ?
    WHERE collector_account_pk = ?;
    """,[int(time.time()),collector_account_pk])
    conn.commit()
    print(str(datetime.now())+": function last_time_media_scraped finished")

