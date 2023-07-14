"""
Inits the summary bot. It starts a Reddit instance using PRAW, gets the latest posts
and filters those who have already been processed.
"""
import argparse
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from pythorhead import Lemmy

import requests
import tldextract
from pythorhead.types import SortType, ListingType

import scraper
import summary
from utils import PostUtils

# We don't reply to posts which have a very small or very high reduction.
MINIMUM_REDUCTION_THRESHOLD = 50
MAXIMUM_REDUCTION_THRESHOLD = 96

# File locations
POSTS_LOG = "./assets/processed_posts.txt"
BLOCKLIST_FILE = "./assets/blocklist.txt"

# Templates.
TEMPLATE = open("./templates/en.txt", "r", encoding="utf-8").read()

HEADERS = {"User-Agent": "Summarizer v2.0"}


def load_blocklist():
    """Reads the processed posts log file and creates it if it doesn't exist.

    Returns
    -------
    list
        A list of domains that are confirmed to have an 'article' tag.

    """

    with open(BLOCKLIST_FILE, "r", encoding="utf-8") as log_file:
        return log_file.read().splitlines()


def load_log():
    """Reads the processed posts log file and creates it if it doesn't exist.

    Returns
    -------
    list
        A list of Reddit posts ids.

    """

    try:
        with open(POSTS_LOG, "r", encoding="utf-8") as log_file:
            return log_file.read().splitlines()

    except FileNotFoundError:
        with open(POSTS_LOG, "a", encoding="utf-8") as log_file:
            return []


def update_log(post_id):
    """Updates the processed posts log with the given post id.

    Parameters
    ----------
    post_id : str
        A Reddit post id.

    """

    with open(POSTS_LOG, "a", encoding="utf-8") as log_file:
        log_file.write("{}\n".format(post_id))


def run_bot(domain, username, password):
    processed_posts = load_log()
    blocklist = load_blocklist()
    lemmy = Lemmy(domain)
    PostUtils.safe_api_call(lemmy.log_in, username_or_email=username, password=password)
    posts = PostUtils.get_posts_deep(lemmy, sort=SortType.New, type_=ListingType.Local)
    logging.info(f"LOADED the latest {len(posts)} posts")
    for post in posts:
        post_id = str(post['id'])
        if 'url' in post and post_id not in processed_posts:
            clean_url = post['url'].replace("amp.", "")
            ext = tldextract.extract(clean_url)
            domain = "{}.{}".format(ext.domain, ext.suffix)
            if domain in blocklist:
                logging.debug(f"BLOCKLIST domain: {domain} from {clean_url} on {post['ap_id']}")
                continue

            logging.info(f"SUMMARIZE domain: {domain} from {clean_url} on {post['ap_id']}")

            try:
                with requests.get(clean_url, headers=HEADERS, timeout=10) as response:
                    if response.headers['content-type'] in (
                            'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/mp4'):
                        logging.info(f"BLOCK Content-Type: {response.headers['content-type']}")
                        update_log(post_id)
                        continue

                    # Most of the times the encoding is utf-8 but in edge cases
                    # we set it to ISO-8859-1 when it is present in the HTML header.
                    if "iso-8859-1" in response.text.lower():
                        response.encoding = "iso-8859-1"
                    elif response.encoding == "ISO-8859-1":
                        response.encoding = "utf-8"

                    html_source = response.text

                article_title, article_date, article_body = scraper.scrape_html(html_source)

                summary_dict = summary.get_summary(article_body)
            except Exception:
                logging.exception(f"Failed to process post {post_id}:{post['ap_id']} for domain {domain}")
                update_log(post_id)
                continue

            # To reduce low quality submissions, we only process those that made a meaningful summary.
            if MINIMUM_REDUCTION_THRESHOLD <= summary_dict["reduction"] <= MAXIMUM_REDUCTION_THRESHOLD:

                # We start creating the comment body.
                post_body = "\n\n".join(
                    ["> " + item for item in summary_dict["top_sentences"]])

                top_words = ""

                for index, word in enumerate(summary_dict["top_words"]):
                    top_words += "{}^#{} ".format(word, index + 1)

                comment = TEMPLATE.format(
                    article_title, clean_url, summary_dict["reduction"], article_date, post_body)

                # PostUtils.safe_api_call(lemmy.comment.create, post['id'], comment, language_id=LanguageType.EN)
                logging.info(f"Will add new comment to post {post['ap_id']} : {comment}")
                update_log(post_id)
            else:
                update_log(post_id)
                logging.info(f"Skipped:{post_id}, Reduction was {summary_dict['reduction']}")


def init():
    """Inits the bot."""
    # Get and parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--domain", default=os.environ.get("INSTANCE_URL"))
    parser.add_argument("--username", default=os.environ.get("BOT_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("BOT_PASSWORD"))
    parser.add_argument("--sleep", default=os.environ.get("BOT_SLEEP_SECS"))
    args = parser.parse_args()
    # if not args.domain or not args.username or not args.password or not args.sleep:
    #     exit(parser.print_usage())

    logging.root.handlers = []
    logging.basicConfig(
        level=(logging.DEBUG if args.verbose > 0 else logging.INFO),
        format="%(asctime)s  %(name)s :: %(levelname)s :: %(message)s",
        handlers=[
            RotatingFileHandler('logs/summary_bot.log', maxBytes=10 * 1000 * 1000, backupCount=10),
            logging.StreamHandler()
        ]
    )
    logging.info("Starting Up...")

    # Don't forget to specify the correct model for your language.

    while True:
        run_bot(args.domain, args.username, args.password)
        logging.info(f"Done summarizing posts, will sleep for {args.sleep} seconds...")
        time.sleep(int(args.sleep))


if __name__ == "__main__":
    init()
