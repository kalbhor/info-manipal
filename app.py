import os
import scraper.slcm as scraper
import parser.parser as parser
import parser.responses as responses
import parser.dbase as database
import requests
import fbmq
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from wit import Wit


### CONFIGS ###
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
page = fbmq.Page(os.environ["PAGE_ACCESS_TOKEN"])
wit_client = Wit(os.environ["WIT_TOKEN"])
dbase = database.handler(db)
responder = responses.messages()


### DB Skeleton ###
class User(db.Model):
    fbid = db.Column(db.String(80), primary_key=True)
    rollno = db.Column(db.String(80), unique=True, nullable=True)
    password = db.Column(db.String(80), nullable=True)
    group = db.Column(db.String(80), nullable=True)
    name = db.Column(db.String(80), nullable=True)

    def __init__(self, fbid, rollno=None, password=None, group=None, name=None):
        self.fbid = fbid
        self.rollno = rollno
        self.password = password
        self.group = group
        self.name = name

    def __repr__(self):
        return '< <Name>{} <Rollno>{} >'.format(self.name, self.rollno)

### Handles Fb verification ###
@app.route('/', methods=['POST'])
def webhook():
    page.handle_webhook(request.get_data(as_text=True))
    return "ok"

@page.handle_delivery
def delivery_handler(payload):
    print("Message delivered")

### Main method (Handles user messages, db) ###
@page.handle_message
def message_handler(event):
    """:type event: fbmq.Event"""
    sender_id = event.sender_id
    message = event.message_text

    ### get user sending request ###
    client = User.query.filter_by(fbid=sender_id).first()

    if client is None:
        ### User doesn't exist on DB ###
        user = User(sender_id)
        dbase.new_user(sender_id, user)
        page.send(sender_id, responder.menu)
        page.send(sender_id, responder.new_user)
    else:
        user = User.query.filter_by(fbid = sender_id).first()
        if user.rollno  == None:
            ### User has entered regno ###
            dbase.regno(message, user)
            page.send(sender_id, responder.new_user_pass)
        elif user.password == None:
            ### User has entered password ###
            dbase.password(message, user)

            if scraper.login(user.rollno, user.password) is None:
                    ### Remove record if wrong details have been entered ###
                    ### Goes back to step 1 (Enter regno) ###
                    dbase.delete(user)
                    page.send(sender_id, responder.wrong)
            else:
                    driver = scraper.login(user.rollno, user.password)
                    group = scraper.group(driver)
                    dbase.group(group, user)
                    page.send(sender_id, responder.verified)

        else:
            user = User.query.filter_by(fbid = sender_id).first()

            page.typing_on(sender_id)
            resp = parser.witintent(message, wit_client)
            print(resp)
            if resp != {}:
                driver = scraper.login(user.rollno, user.password)
                if driver is None:
                    dbase.delete(user)
            else:
                page.send(sender_id, message)
                page.send(sender_id, responder.default)
            ### Parsing responses begins here ###

            if 'greetings' in resp:
                page.send(sender_id, 'Hodor!')

            if 'thanks' in resp:
                page.send(sender_id, "You're welcome!")

            if 'guardian' in resp:
                guardian_data = scraper.guardian(driver)
                response = parser.guardian(resp, guardian_data)
                page.send(sender_id, str(response))

            if 'timetable' in resp:
                timetable_data = scraper.timetable(driver)
                response = parser.timetable(resp, timetable_data)
                page.send(sender_id, str(response))

            if 'attendance' in resp or 'subject' in resp:
                group = user.group
                attendance_data = scraper.attendance(driver)
                response = parser.attendance(resp, attendance_data, group)
                page.send(sender_id, str(response))

            if 'curse' in resp:
                page.send(sender_id, responder.curse)



@page.after_send
def after_send(payload, response):
    print("Done")


if __name__ == '__main__':
    app.run(debug=True)
