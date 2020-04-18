#!/usr/bin/env python3

import praw
import re
from usps import USPSApi, Address
import logging
import sql_library as sql

USPS_USERID = '256PERSO0573'

# Get at https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID = ""
REDDIT_CLIENT_SECRET = ""
REDDIT_USERNAME = ""
REDDIT_PASSWORD = "!"

# Careful as you release this into the wild!
SUB_TO_MONITOR = "test"

REPLY_TEMPLATE = "ZIP Code {zip} is {city}, {state}"
REPLY_INVALID_TEMPLATE = '{zip} is not a valid ZIP code, according to the USPS.'
REPLY_TAG = '\n\n^(Created by u/grtgbln)'

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

usps = USPSApi(USPS_USERID)

db = sql.SQL(sql_type='SQLite', sqlite_file='zip_code_entries.db')

reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET,
                     user_agent='ZipCodeBot (by u/grtgbln)', username=REDDIT_USERNAME, password=REDDIT_PASSWORD)
if not reddit.read_only:
    logging.info("Connected and running.")


def search_zip(zip_code):
    zip = usps.lookup_city_by_zip(str(zip_code), just_answer=True)
    return zip.result


def get_zip_code(body):
    return re.findall('\b\d{5}\b', body)


def reply_with_loc(submission, loc, zip_code):
    try:
        return submission.reply(REPLY_TEMPLATE.format(zip=zip_code, city=loc['City'], state=loc['State']) + REPLY_TAG)
    except Exception as e:
        logging.error(e)
        return None


def reply_invalid(submission, zip_code):
    try:
        return submission.reply(REPLY_INVALID_TEMPLATE.format(zip=zip_code) + REPLY_TAG)
    except Exception as e:
        logging.error(e)
        return None


def process(entry_type, entry, text):
    zips = get_zip_code(text)
    if zips:
        zip_code = zips[0]
        if not check_if_already_in_db(entry_type=entry_type, entry_id=entry.id):
            loc = search_zip(zip_code)
            if loc and loc != 'Invalid Zip Code.':
                comment = reply_with_loc(entry, loc, zip_code)
                if comment:
                    _ = store_entry_in_db(entry_type, entry.id)
                    logging.info(f'Replied with location: {comment.permalink}.')
                else:
                    logging.error("Couldn't reply to valid location.")
            else:
                comment = reply_invalid(entry, zip_code)
                if comment:
                    _ = store_entry_in_db(entry_type, entry.id)
                    logging.info(f'Replied to invalid ZIP: {comment.permalink}.')
                else:
                    logging.error("Couldn't reply to invalid location.")
        else:
            logging.info(f"Already replied to this {entry_type}")
    else:
        logging.debug("No ZIP codes found.")


def check_if_already_in_db(entry_type, entry_id):
    if entry_type == 'submission':
        results = db.custom_query(queries=[f"SELECT id FROM submissions WHERE id = '{str(entry_id)}'"])
        if results and results > 0:
            return True
        return False
    elif entry_type == 'comment':
        results = db.custom_query(queries=[f"SELECT id FROM comments WHERE id = '{str(entry_id)}'"])
        if results and results > 0:
            return True
        return False
    else:
        logging.info("entry_type is not 'submission' or 'comment', skipping entry...")
        return True


def store_entry_in_db(entry_type, entry_id):
    if entry_type == 'submission':
        results = db.custom_query(queries=[f"INSERT INTO submissions (id) VALUES ('{str(entry_id)}')"], commit=True)
        if results and results > 0:
            return True
        return False
    elif entry_type == 'comment':
        results = db.custom_query(queries=[f"INSERT INTO comments (id) VALUES ('{str(entry_id)}')"], commit=True)
        if results and results > 0:
            return True
        return False
    else:
        logging.error("Couldn't store entry in database.")
        return False


def clean_db():
    results = db.custom_query(queries=['DELETE FROM submissions', 'DELETE FROM comments'], commit=True)
    if results >= 0:
        logging.info('Database cleared.')
        return True
    logging.error('Database could not be cleared.')
    return False


def run():
    # clean_db()
    subreddit = reddit.subreddit(SUB_TO_MONITOR)
    comment_stream = subreddit.stream.comments(pause_after=-1)
    submission_stream = subreddit.stream.submissions(pause_after=-1)
    while True:
        for comment in comment_stream:
            if comment is None:
                break
            if comment.author and comment.author.name and comment.author.name != REDDIT_USERNAME:
                process(entry_type='comment', entry=comment, text=comment.body)
        for submission in submission_stream:
            if submission is None:
                break
            if submission.is_self and submission.author and submission.author.name and submission.author.name != REDDIT_USERNAME:
                process(entry_type='submission', entry=submission, text=submission.selftext)


run()
