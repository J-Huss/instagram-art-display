from PIL import Image
from PIL import ImageTk
import tkinter as tk
from tkinter import ttk
import tkvideo
import sv_ttk
import cv2
import os
from datetime import datetime
import ctypes
import platform
import time
import threading
import tensorflow as tf
import numpy as np
from tensorflow.keras.models import load_model
import instagrapi

import db
import media_handler
import ml_training

### /// currently outcommented some threads within start function

class DisplayApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Art Display")
        sv_ttk.use_dark_theme()
        self.fullscreen = tk.Toplevel(self.window)
        self.fullscreen.withdraw()
        self.fullscreen.bind("<Key>", self.end_fullscreen)
        self.fullscreen.bind("<Button-1>", self.end_fullscreen)
        
        self.window.after(0, lambda: self.window.wm_state('zoomed'))
        self.window.after(0,self.window.lift)
        self.work_img_path = "work_file.jpg"
        self.work_video_path = "work_file.mp4"

        # if condition code: work around to make title bar dark as well; only works on Windows(10?)
        # this makes booting up a bit 'jumpy' sometime, but tradeoff for having this jumpy part only in the beginning vs white title bar all the time
        # https://gist.github.com/Olikonsti/879edbf69b801d8519bf25e804cec0aa?permalink_comment_id=4416827#gistcomment-4416827
        if platform.system() == "Windows" and int(platform.release()) == 10:
            self.window.update()
            self.window.iconify()
            DWWMA_USE_IMMERSIVE_DARK_MODE = 20
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            get_parent = ctypes.windll.user32.GetParent
            hwnd = get_parent(self.window.winfo_id())
            rendering_policy = DWWMA_USE_IMMERSIVE_DARK_MODE
            value = 2
            value = ctypes.c_int(value)
            set_window_attribute(hwnd, rendering_policy, ctypes.byref(value), ctypes.sizeof(value))
            self.window.update_idletasks()
            self.window.deiconify()

        ### TODO: integrate into settings function
        # slideshow & scraping settings
        self.timer_hours = 0
        self.timer_minutes = 0
        self.timer_seconds = 30
        self.intervall_update_followee_list = 604800  # one week in seconds
        self.intervall_reg_scraping = 10800 #3 hours in seconds

        self.state_slideshow_running = bool

        self.button_fullscreen = ttk.Button(self.window,command=self.button_toggle_fullscreen_function,text="fullscreen")
        self.button_fullscreen.place(relx=0.95, rely=0.95, anchor='center')

        self.button_dont_show_again = ttk.Button(self.window,command=self.button_dont_show_again_function,text="don't show this again",width=20)
        self.button_dont_show_again.place(relx=0.07, rely=0.91, anchor='center')

        self.button_is_favorite = ttk.Button(self.window,command=self.button_is_favorite_function,text="add to favorites",width=20) # setting 'add to favorites' as default emtpy state since more media will be non-favorite than favorite
        self.button_is_favorite.place(relx=0.93, rely=0.05, anchor='center')

        self.button_show_next_media = ttk.Button(self.window,command=self.next_media,text="show next media",width=20)
        self.button_show_next_media.place(relx=0.07, rely=0.95, anchor='center')

        self.button_slideshow = ttk.Button(self.window,command=self.button_slideshow_start_function,text="start slideshow",width=20)
        self.button_slideshow.place(relx=0.07,rely=0.05,anchor='center')

        self.window.protocol("WM_DELETE_WINDOW",self.closing_function) 


        self.window.after(200, lambda: self.get_random_media())

    def setup(self):
        print(str(datetime.now())+": function setup started")
        
        ### TODO: welcome prompt
        ### TODO: showing small text label with progress steps; constantly updating text and then destroying it
        
        if os.path.isfile(db.DB_PATH) is True:
            print(str(datetime.now())+": database exists")
        ### else: 
        ### TODO: asks for file path; save this to variable and to config json
        ### TODO: create new db with #db.init_all_tables()
        # currently no else statement needed, since db.setup_connection creates new db, if there's none existing for coll_acc_pk
        
        
        if db.check_first_setup_done() is True:
                print(str(datetime.now())+": function setup finished")
                return
        # else:
            ### TODO: setup functions
            ### get collector account pk
            ### get followee list
            ### scrape initial media amount
            ### set first setup done to 1

        ### TODO: integrate this into setting option
        self.ml_pred_enabled = True

        if self.ml_pred_enabled is True:
            print(str(datetime.now())+": ML prediction enabled")
            ### set display settings to only show media type 1?
            self.ml_model = load_model(db.config["ml_model_path"])

        print(str(datetime.now())+": function setup finished")

    def get_random_media(self):
        print(str(datetime.now())+": function get_random_media started")

        while True:
            try:
                self.curr_media_obj=media_handler.media(*media_handler.load_db_media_values(db.get_random_media()))
                self.curr_media_obj.load_file()
            except instagrapi.exceptions.MediaNotFound:
                print(str(datetime.now())+": media post doesn't exist on Instagram anymore; deleting entry from db and getting new one")
                db.conn.execute("DELETE FROM media WHERE media_pk = (?)",[self.curr_media_obj.media_pk])
                db.conn.execute("DELETE FROM accounts_medias WHERE media_pk = (?)",[self.curr_media_obj.media_pk])
                db.conn.commit()
                continue

            if self.ml_pred_enabled is False:
                break

            else: # ml_pred enabled

                self.pred_img = cv2.imread(self.curr_media_obj.file_path)
                self.pred_img = tf.image.resize(self.pred_img, (256,256))
                prediction = self.ml_model.predict(np.expand_dims(self.pred_img/255, 0))
                prediction_value = float(prediction)
                print(str(datetime.now())+": prediction value is "+str(prediction_value))
                if prediction_value < 0.5:
                    print(str(datetime.now())+": prediction value is < 0.5, image likely 'show again'")
                    break
                else:
                    print(str(datetime.now())+": prediction value is not < 0.5 and likely 'dont show again'; getting next image")
                    continue
        

        self.init_media_labels()
        if self.curr_media_obj.is_favorite == 1:
            self.button_is_favorite.configure(text="remove from favorites")
        else:
            self.button_is_favorite.configure(text="add to favorites")

        if self.curr_media_obj.dont_show_again == 1:
            self.button_dont_show_again.configure(text="show this again")
        else:
            self.button_dont_show_again.configure(text="don't show this again")
        db.set_last_shown(self.curr_media_obj.media_pk)



    def closing_function(self):
        self.state_slideshow_running = False # workaround because setting deamon thread for slideshow is not working when using tkinter
        db.conn.close()
        self.window.destroy()

    def button_toggle_fullscreen_function(self):
        print(str(datetime.now())+": button fullscreen pressed")
        self.fullscreen.deiconify()
        self.fullscreen.attributes("-fullscreen",True)
        self.fullscreen.after(0,self.fullscreen.lift)

    def end_fullscreen(self,event=None):
        print(str(datetime.now())+": event & function end_fullscreen triggered")
        self.fullscreen.withdraw()

    def button_dont_show_again_function(self):
        print(str(datetime.now())+": button dont show again pressed")
        if self.curr_media_obj.dont_show_again == 1:
            bool_int = 0
        else:
            bool_int = 1
        self.curr_media_obj.dont_show_again = bool_int
        db.set_dont_show_again_bool(bool_int,self.curr_media_obj.media_pk)
        if self.curr_media_obj.dont_show_again == 1: # change button text according to new state 
            self.button_dont_show_again.configure(text="show this again",width=20)
        else:
            self.button_dont_show_again.configure(text="don't show this again",width=20)

    def button_is_favorite_function(self):
        print(str(datetime.now())+": button set to favorite pressed")
        if self.curr_media_obj.is_favorite == 1:
            bool_int = 0
        else:
            bool_int = 1
        self.curr_media_obj.is_favorite = bool_int
        db.set_is_favorite_bool(bool_int,self.curr_media_obj.media_pk)
        if self.curr_media_obj.is_favorite == 1: # change button text according to new state 
            self.button_is_favorite.configure(text="remove from favorites")
        else:
            self.button_is_favorite.configure(text="add to favorites")

    def slideshow_loop(self):
        time.sleep(1) # otherwise the switch feels too drastic
        self.state_slideshow_running = True
        timer = self.timer_hours * 3600 + self.timer_minutes * 60 + self.timer_seconds
        while self.state_slideshow_running:
                print(str(datetime.now())+": slideshow_loop running")
                self.next_media()
                time.sleep(timer)

    def button_slideshow_start_function(self):
            print(str(datetime.now())+": button slideshow started pressed")
            self.thread_slideshow = threading.Thread(target=self.slideshow_loop)
            self.button_slideshow.configure(command=self.button_slideshow_stop_function,text="stop slideshow",width=20)
            self.window.after(0,self.thread_slideshow.start())

    def button_slideshow_stop_function(self):
        print(str(datetime.now())+": button slideshow stopped pressed")
        self.state_slideshow_running = False
        self.button_slideshow.configure(command=self.button_slideshow_start_function,text="start slideshow",width=20)

    def init_media_labels(self):
        # needs completely different if/else setups for different media_types, since different type of labels need to be created
        ### TODO: currently works for most screens with just hardcoding the resizing; later add: relative amount
        if self.curr_media_obj.media_type == 1:
            print(str(datetime.now())+": creating labels for image")
            self.work_img = Image.open(self.work_img_path)
            self.img = ImageTk.PhotoImage(Image.open(self.work_img_path).resize([int(Image.open(self.work_img_path).width*0.65),int(Image.open(self.work_img_path).height*0.65)]))
            self.media_label = ttk.Label(self.window,image=self.img)
            self.media_label.place(relx=0.5, rely=0.5, anchor='center')

            if self.work_img.height > self.window.winfo_screenheight():
                print(str(datetime.now())+": image height is bigger than screen")
                self.factor = self.window.winfo_screenheight() / self.work_img.height
            else:
                print(str(datetime.now())+": image height is not bigger than screen")
                self.factor = 1
            
            self.img_fs= ImageTk.PhotoImage(Image.open(self.work_img_path).resize([int(self.work_img.width*self.factor),int(self.work_img.height*self.factor)])) # resize
            self.media_label_fs = ttk.Label(self.fullscreen,image=self.img_fs)
            self.media_label_fs.place(relx=0.5, rely=0.5, anchor='center')

        else:
            print(str(datetime.now())+": creating labels for video")
            # getting video resolution
            video = cv2.VideoCapture(self.work_video_path)
            self.video_width = video.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.video_height = video.get(cv2.CAP_PROP_FRAME_HEIGHT)

            self.media_label = ttk.Label(self.window)
            self.media_label.place(relx=0.5, rely=0.5, anchor='center')
            player = tkvideo.tkvideo(self.work_video_path, self.media_label, loop = 1,size=(int(self.video_width*0.65),int(self.video_height*0.65))) 
            player.play()

            self.media_label_fs = ttk.Label(self.fullscreen)
            self.media_label_fs.place(relx=0.5, rely=0.5, anchor='center')
            
            if self.video_height > self.window.winfo_screenheight():
                print("video height is bigger than screen")
                self.factor = self.window.winfo_screenheight() / self.video_height
            else:
                print("video height is not bigger than screen")
                self.factor = 1
            
            player = tkvideo.tkvideo(self.work_video_path, self.media_label_fs, loop = 1,size=(int(self.video_width*self.factor),int(self.video_height*self.factor)))
            player.play()

    def next_media(self):
        print(str(datetime.now())+": button next media pressed")
        # if deleting of dont_show_again enabled: allow for deletion of old media from storage before getting the new one:
        
        if self.curr_media_obj.dont_show_again == 1 and media_handler.saving_dont_show_again_enabled is False:
            print(str(datetime.now())+": trying to delete media from storage")
            try:
                os.remove(self.curr_media_obj.file_path)
                print(str(datetime.now())+": "+str(self.curr_media_obj.media_pk)+" successfully deleted from storage")
            except OSError:
                print(str(datetime.now())+": deleting failed")

        # destroying the old labels before creating new ones instead of replacing them
        self.media_label.destroy()
        self.media_label_fs.destroy()

        self.get_random_media()

    def reg_scraping(self):
        ### TODO: hard-coded scraping amount for now; later: install loop with media counter limit
        ### OR integrate time stamps of posts and scrape till latest post saved of users
        while True:
            print(str(datetime.now())+": function reg_scraping started")
            time_passed =  int(time.time()) - db.get_last_time_media_scraped(db.ACTIVE_COLL_ACC_PK)
            if time_passed > self.intervall_reg_scraping:
                print(str(datetime.now())+": time_passed bigger than defined intervall; starting scraping")
                
                #media_handler.get_X_from_all_users(3)
                
                db.set_last_time_media_scraped(db.ACTIVE_COLL_ACC_PK) 
                print(str(datetime.now())+": finished scraping and finished function reg_scraping")

            else:
                delta = self.intervall_reg_scraping - time_passed + 1
                print(str(datetime.now())+": time_passed smaller than defined intervall; sleeping for "+str(delta)+" seconds till intervall is reached")
                time.sleep(delta)

    def update_followee_list(self):
        """only check for updating necessity once per app init"""
        print(str(datetime.now())+": function update_followee_list started")
        time_passed =  int(time.time()) - db.get_last_time_followee_list_updated(db.ACTIVE_COLL_ACC_PK)
        if time_passed > self.intervall_update_followee_list:
            print(str(datetime.now())+": time_passed bigger than defined intervall; starting updating now")
            media_handler.get_followee_list()
            print(str(datetime.now())+": finished function update_followee_list")
        else:
            print(str(datetime.now())+": time_passed smaller than defined intervall; finished function update_followee_list")

    def start(self):
        # set 2nd thread to 2 minutes after testing to avoid running synch to update followee list; next iteration: solve with event handling: only start running when other thread finished 
        print(str(datetime.now())+": initializing DisplayApp")
        self.setup()
        #self.thread_update_followee_list = threading.Thread(target=self.update_followee_list)
        #self.window.after(5000, lambda: self.thread_update_followee_list.start())

        #self.thread_reg_scraping = threading.Thread(target=self.reg_scraping)
        #self.window.after(10000, lambda: self.thread_reg_scraping.start())

        self.thread_ml_training = threading.Thread(target=ml_training.full_training)
        self.window.after(5000, lambda: self.thread_ml_training.start())

        self.window.mainloop()


if __name__ == "__main__":
    DisplayApp=DisplayApp()
    DisplayApp.start()
