#!/usr/bin/env python3

from bs4 import BeautifulSoup, Tag
from datetime import datetime
import logging
import re
import requests

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
WHITE = "\033[97m"

TEAMS = {
    "ATL": ["atl", "atlanta", "hawks"],
    "BOS": ["bos", "boston", "celtics"],
    "BKN": ["bkn", "brooklyn", "nets"],
    "CLE": ["cle", "cleveland", "cavaliers", "cavs"],
    "CHA": ["cha", "charlotte", "hornets"],
    "CHI": ["chi", "chicago", "bulls"],
    "DAL": ["dal", "dallas", "mavericks", "mavs"],
    "DEN": ["den", "denver", "nuggets"],
    "DET": ["det", "detroit", "pistons"],
    "GSW": ["gsw", "golden", "state", "warriors"],
    "HOU": ["hou", "houston", "rockets"],
    "IND": ["ind", "indiana", "pacers"],
    "LAC": ["lac", "clippers"],
    "LAL": ["lal", "lakers"],
    "MEM": ["mem", "memphis", "grizzlies"],
    "MIA": ["mia", "miami", "heat"],
    "MIL": ["mil", "milwaukee", "bucks"],
    "MIN": ["min", "minnesota", "timberwolves", "wolves"],
    "NOP": ["nop", "orleans", "pelicans", "no", "nola", "pels"],
    "NYK": ["nyk", "york", "knicks", "nyc", "ny"],
    "OKC": ["okc", "oklahoma", "thunder"],
    "ORL": ["orl", "orlando", "magic"],
    "PHI": ["phi", "philadelphia", "sixers"],
    "PHX": ["phx", "phoenix", "suns", "pho"],
    "POR": ["por", "portland", "trailblazers", "blazers"],
    "SAC": ["sac", "sacramento", "kings"],
    "SAS": ["sas", "san", "antonio", "spurs"],
    "TOR": ["tor", "toronto", "raptors"],
    "UTA": ["uta", "utah", "jazz"],
    "WAS": ["was", "washington", "wizards"],
}


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
    url = f"https://forum.hardware.fr/hfr/Discussions/Sports/basket-nba-prono-sujet_20548_{page}.htm"
    response = requests.get(url=url)
    response.raise_for_status()
    logger.info("")
    logger.info(f"{WHITE}FETCHED:{RESET} page {page}")
    return BeautifulSoup(response.content, "html.parser")


def get_last_page(soup: BeautifulSoup) -> int:
    tr = soup.find("tr", class_="cBackHeader fondForum2PagesHaut")
    div = tr.find("div", class_="left")
    return int(div.contents[-1].string)


def get_messages(soup: BeautifulSoup):
    entries = {}
    messages = soup.find_all("tr", class_="message")
    for message in messages:
        try:
            entry = parse_message(message)
            entries[entry["id"]] = entry
            logger.info(f"{GREEN}ACCEPT{RESET}: {entry['results']}")
        except AssertionError as e:
            logger.info(f"{RED}DISCARD{RESET}: {e}")
    return entries


def parse_date(message: Tag) -> datetime:
    date_tag = message.find("td", class_="messCase2").div.div
    date_string = next(date_tag.stripped_strings)
    format = "Posté le %d-%m-%Y à %H:%M:%S"
    return datetime.strptime(date_string, format)


def cleanup_text(text: Tag) -> list[str]:
    cleanup = []
    cleanup += text.find_all("div")  # removes quotes
    cleanup += text.find_all("img")  # removes images
    cleanup += text.find_all("span")  # removes signatures
    for tag in cleanup:
        tag.decompose()


WORD_REGEX = re.compile(r"\b\w{2,}\b")
SCORE_REGEX = re.compile(r"(?<!\()\b[0-4]\b(?!\))")
# (?<!\() negative lookbehind to ensure the digit is not preceeded by an opening parenthesis
# (?!\)) negative lookahead to ensure the digit is not followed by a closing parenthesis
# this is because Piccolo likes to write team seeds, otherwise the regex could just be \b[0-4]\b


def parse_line(line: str) -> dict:
    line = line.casefold()
    teams = []
    words = re.findall(WORD_REGEX, line)
    for word in words:
        for team, names in TEAMS.items():
            if word in names and team not in teams:
                teams.append(team)
                break
    scores = [int(n) for n in re.findall(SCORE_REGEX, line)]
    assert teams, "no team found"
    assert scores, "no score found"
    assert len(teams) == 2, f"must have exactly two teams {teams}"
    assert len(scores) == 2, f"must have exactly two scores {scores}"
    assert scores.count(4) == 1, f"exactly one score must be 4 {scores}"
    winner = teams[0] if scores[0] > scores[1] else teams[1]
    return {"result": (winner, sum(scores)), "teams": tuple(teams), "scores": tuple(scores)}


def parse_message(tag: Tag):
    metadata = tag.find("td", class_="messCase1")
    user = metadata.b.string.strip()
    logger.info("")
    if not metadata.a:
        logger.info(f"MESSAGE: {user}")
        raise AssertionError("advertisement.")
    id = metadata.a.get("name")[1:]
    date = parse_date(tag)
    logger.info(f"MESSAGE: {date} #{id} {WHITE}{user}{RESET}")
    text = tag.find("div", id=f"para{id}")
    cleanup_text(text)
    series = []
    lines = list(text.stripped_strings)
    if lines and lines[0] == "Reprise du message précédent :":
        raise AssertionError("skipping first message of new page (duplicate).")
    for line in lines:
        try:
            data = parse_line(line)
            logger.info(f"{BLUE}MATCH{RESET}: {data} ({line})")
            series.append(data.get("result"))
        except AssertionError as e:
            logger.info(f"{YELLOW}DISCARD{RESET}: {e} ({line})")

    assert len(series) > 0, "no series found."
    assert len(series) == 15, f"number of series must be 15, found {len(series)}."
    return {"user": user, "id": id, "date": date, "results": tuple(series)}


if __name__ == "__main__":
    logger = setup_logging(logging.INFO)
    entries = {}
    start_page = 6652
    last_page = 0
    LIMIT = 5
    for page in range(start_page, start_page + LIMIT):
        soup = fetch_soup(page)
        entries.update(get_messages(soup))
        if not last_page:
            last_page = get_last_page(soup)
        if page >= last_page:
            break

    logger.info("")
    logger.info(f"{WHITE}EXPORT{RESET}:")
    sep = ","
    for id in entries:
        results = sep.join([f"{winner}{sep}{score}" for winner, score in entries[id]["results"]])
        print(f"{WHITE}{entries[id]['user']}{RESET}{sep}{sep}{results}")
