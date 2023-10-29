import sqlalchemy as sqa
import json

with open('config.json', 'r') as config_file:
    config = json.load(config_file)

ACTIVE_COLL_ACC_STR = config['active_coll_acc_str']
ACTIVE_COLL_ACC_PK = "" # will be filled through media_handler file

class DBManager():
    def __init__(
            self,
            connection_path
    ):
        self.connection_path = connection_path
        self.engine = sqa.create_engine(self.connection_path,echo=True)
        self.connection = self.engine.connect()
        self.metadata = sqa.MetaData()


    def create_db(self):
        
        self.settings = sqa.Table(
            "settings",self.metadata,
            sqa.Column("collector_account_pk",sqa.Integer,primary_key=True),
            sqa.Column("collector_account_str",sqa.String),
            sqa.Column("first_setup_done",sqa.Integer,default=0),
            sqa.Column("last_time_followee_list_updated",sqa.Integer,default=0),
            sqa.Column("last_time_media_scraped",sqa.Integer,default=0)
        )

        self.user = sqa.Table(
            "user",self.metadata,
            sqa.Column("user_pk",sqa.Integer,primary_key=True),
            sqa.Column("user_name",sqa.String),
            sqa.Column("is_private",sqa.Integer),
            sqa.Column("external_url",sqa.String)
        )

        self.media = sqa.Table(
            "media",self.metadata,
            sqa.Column("media_pk",sqa.Integer,primary_key=True),
            sqa.Column("media_id",sqa.Integer),
            sqa.Column("media_code",sqa.String),
            sqa.Column("media_type",sqa.Integer),
            sqa.Column("user_pk",sqa.Integer),
            sqa.Column("position_in_album",sqa.Integer),
            sqa.Column("parent_pk",sqa.Integer),
            sqa.Column("caption_text",sqa.String)
        )

        self.accounts_users = sqa.Table(
            "account_users",self.metadata,
            sqa.Column("collector_acc_pk",sqa.Integer),
            sqa.Column("user_pk",sqa.Integer),
            sqa.Column("user_excluded",sqa.Integer,default=0)
        )

        self.accounts_medias = sqa.Table(
            "accounts_medias",self.metadata,
            sqa.Column("collector_account_pk",sqa.Integer),
            sqa.Column("media_pk",sqa.Integer),
            sqa.Column("is_favorite",sqa.Integer,default=0),
            sqa.Column("dont_show_again",sqa.Integer,default=0),
            sqa.Column("last_shown",sqa.Integer),
            sqa.Column("ml_split_type",sqa.Integer),
            sqa.Column("ml_train_time",sqa.Integer),
            sqa.Column("ml_train_skipped",sqa.Integer),
        )

        self.metadata.create_all(self.engine)


    def load_table_objects(self):
        self.settings = sqa.Table("settings",self.metadata,autoload_with=self.engine)
        self.user = sqa.Table("user",self.metadata,autoload_with=self.engine)
        self.media = sqa.Table("media",self.metadata,autoload_with=self.engine)
        self.accounts_users = sqa.Table("accounts_users",self.metadata,autoload_with=self.engine)
        self.accounts_medias = sqa.Table("accounts_medias",self.metadata,autoload_with=self.engine)


if __name__ == "__main__":
    DBManager = DBManager(connection_path="sqlite:///"+config['db_path'])
    DBManager.load_table_objects()

