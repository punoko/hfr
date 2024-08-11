#!/usr/bin/env python3

from bs4 import BeautifulSoup, Tag
from datetime import datetime
import logging
import re
import requests
from collections import defaultdict

TOPIC_BASE_URL = "https://forum.hardware.fr/hfr/Discussions/Sports/olympiques-objectif-medailles-sujet_111788"

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
WHITE = "\033[97m"


def setup_logging(level: int) -> logging.Logger:
    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def fetch_soup(page: int) -> BeautifulSoup:
    url = f"{TOPIC_BASE_URL}_{page}.htm"
    response = requests.get(url=url)
    response.raise_for_status()
    logger.info("")
    logger.info(f"{WHITE}FETCHED:{RESET} page {page}")
    return BeautifulSoup(response.text, "html.parser")


def get_last_page(soup: BeautifulSoup) -> int:
    tr = soup.find("tr", class_="cBackHeader fondForum2PagesHaut")
    if tr is None:
        raise ValueError
    div = tr.find("div", class_="left")
    return int(div.contents[-1].string)


def get_messages(soup: BeautifulSoup):
    entries = {}
    # print(soup)
    messages = soup.find_all("tr", class_="message")
    for message in messages:
        try:
            # print(message)
            entry = parse_message(message)
            entries[entry["id"]] = entry
            logger.info(f"{GREEN}ACCEPT{RESET}: ok")
        except AssertionError as e:
            logger.info(f"{RED}DISCARD{RESET}: {e}")
    return entries


def parse_date(message: Tag) -> datetime:
    date_tag = message.find("td", class_="messCase2").div.div
    date_string = next(date_tag.stripped_strings)
    format = "Posté le %d-%m-%Y à %H:%M:%S"
    return datetime.strptime(date_string, format)


def parse_quotes(message: Tag) -> int:
    regex = re.compile(r"Message cité \d+ fois")
    quote_tag = message.find(name="a", class_="cLink", string=regex)
    if not quote_tag:
        return 0
    else:
        quotes = int(next(quote_tag.stripped_strings).split()[2])
        return quotes


def cleanup_text(text: Tag) -> list[str]:
    cleanup = []
    cleanup += text.find_all("div")  # removes quotes
    cleanup += text.find_all("span")  # removes signatures
    for tag in cleanup:
        tag.decompose()


def parse_message(tag: Tag):
    metadata = tag.find("td", class_="messCase1")
    user = metadata.b.string.strip().replace("\u200B", "")
    logger.info("")
    if not metadata.a:
        logger.info(f"MESSAGE: {user}")
        raise AssertionError("advertisement.")
    user_count[user] += 1
    id = int(metadata.a.get("name")[1:])
    date = parse_date(tag)
    quotes = parse_quotes(tag)
    url = f"{TOPIC_BASE_URL}_{page}.htm#t{id}"
    logger.info(f"MESSAGE: {date} #{id} {WHITE}{user}{RESET}\n{url}")
    text = tag.find("div", id=f"para{id}")
    cleanup_text(text)
    images = text.find_all("img")
    for image in images:
        name = image.get("alt")
        if name:
            if name.startswith("http"):
                image_count[name] += 1
            else:
                emote_count[name] += 1
    lines = list(text.stripped_strings)
    if lines and lines[0] == "Reprise du message précédent :":
        raise AssertionError("skipping first message of new page (duplicate).")
    return {"user": user, "id": id, "date": date, "quotes": quotes, "page": page, "url": url}


def print_top(input: list[tuple], num: int):
    threshold = input[num - 1][0] if len(input) > num else 0
    data = [x for x in input if x[0] >= threshold]
    for item in data:
        print(f"{item[0]} {item[1]}")


if __name__ == "__main__":
    logger = setup_logging(logging.INFO)
    entries = {}
    user_count = defaultdict(int)
    emote_count = defaultdict(int)
    image_count = defaultdict(int)
    start_page = 1
    last_page = 0
    LIMIT = 5000
    for page in range(start_page, start_page + LIMIT):
        soup = fetch_soup(page)
        entries.update(get_messages(soup))
        if not last_page:
            last_page = get_last_page(soup)
        if page >= last_page:
            break

    logger.info("")
    logger.info(f"{WHITE}TOP QUOTES{RESET}:")
    quotes = sorted([(x["quotes"], x["url"]) for x in entries.values() if x["quotes"] > 1], reverse=True)
    print_top(quotes, 20)

    logger.info("")
    logger.info(f"{WHITE}TOP USERS{RESET}:")
    users = sorted([(v, k) for k, v in user_count.items() if v > 1], reverse=True)
    print_top(users, 20)

    logger.info("")
    logger.info(f"{WHITE}TOP EMOTES{RESET}:")
    emotes = sorted([(v, k) for k, v in emote_count.items() if v > 1], reverse=True)
    print_top(emotes, 20)

    logger.info("")
    logger.info(f"{WHITE}TOP IMAGES{RESET}:")
    images = sorted([(v, k) for k, v in image_count.items() if v > 1], reverse=True)
    print_top(images, 20)

    minute_count = defaultdict(int)
    hour_count = defaultdict(int)
    for entry in entries.values():
        minute = str(entry["date"])[:-3]
        minute_count[minute] += 1
        hour = str(entry["date"])[:-6]
        hour_count[hour] += 1

    logger.info("")
    logger.info(f"{WHITE}TOP HOURS{RESET}:")
    hours = sorted([(v, k) for k, v in hour_count.items() if v > 1], reverse=True)
    print_top(hours, 20)

    logger.info("")
    logger.info(f"{WHITE}TOP MINUTES{RESET}:")
    minutes = sorted([(v, k) for k, v in minute_count.items() if v > 1], reverse=True)
    print_top(minutes, 20)

