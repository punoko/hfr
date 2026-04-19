# pyright: reportOptionalMemberAccess=false
# pyright: reportAttributeAccessIssue=false

import argparse
import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

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


class InvalidLineError(Exception):
    def __init__(self, err: str) -> None:
        super().__init__(err)


class InvalidMessageError(Exception):
    def __init__(self, err: str) -> None:
        super().__init__(err)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-s", "--start", help="page to start parsing from", type=int)
    parser.add_argument("-p", "--pages", help="number of pages to parse", type=int, default=3)
    parser.add_argument("-q", "--quiet", help="print results only", action="store_true")
    return parser.parse_args()


def url(page: int) -> str:
    base = "https://forum.hardware.fr"
    path = "/hfr/Discussions/Sports/sujet_20548"
    return f"{base}{path}_{page}.htm"


def fetch_soup(page: int) -> BeautifulSoup:
    response = requests.get(url=url(page), timeout=5)
    response.raise_for_status()
    logger.info("")
    logger.info(f"{WHITE}FETCHED:{RESET} page {page}")
    return BeautifulSoup(response.content, "html.parser")


def get_last_page(soup: BeautifulSoup) -> int:
    tr = soup.find("tr", class_="cBackHeader fondForum2PagesHaut")
    div = tr.find("div", class_="left")
    return int(div.contents[-1].string)


def get_messages(soup: BeautifulSoup) -> dict:
    entries = {}
    messages = soup.find_all("tr", class_="message")
    for message in messages:
        try:
            entry = parse_message(message)
            entries[entry["id"]] = entry
            logger.info(f"{GREEN}ACCEPT{RESET}: {entry['results']}")
        except InvalidMessageError as e:
            logger.info(f"{RED}DISCARD{RESET}: {e}")
    return entries


def parse_date(message: Tag) -> datetime:
    date_tag = message.find("td", class_="messCase2").div.div
    date_string = next(date_tag.stripped_strings)
    fmt = "Posté le %d-%m-%Y à %H:%M:%S"
    return datetime.strptime(date_string, fmt)  # noqa: DTZ007


def cleanup_text(text: Tag | None) -> None:
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
    if len(teams) != 2:  # noqa:PLR2004
        raise InvalidLineError(err=f"must have exactly two teams, found {len(teams)}: {teams}")
    if len(scores) != 2:  # noqa:PLR2004
        raise InvalidLineError(err=f"must have exactly two scores, found {len(scores)} {scores}")
    if scores.count(4) != 1:
        raise InvalidLineError(err=f"exactly one score must be 4 {scores}")
    winner = teams[0] if scores[0] > scores[1] else teams[1]
    return {
        "result": (winner, sum(scores)),
        "teams": tuple(teams),
        "scores": tuple(scores),
    }


def parse_message(tag: Tag) -> dict:
    metadata = tag.find("td", class_="messCase1")
    user = metadata.b.string.strip()
    logger.info("")
    if not metadata.a:
        logger.info(f"MESSAGE: {user}")
        raise InvalidMessageError(err="advertisement")
    msg_id = metadata.a["name"][1:]
    date = parse_date(tag)
    logger.info(f"MESSAGE: {date} #{msg_id} '{WHITE}{user}{RESET}'")
    text = tag.find("div", id=f"para{msg_id}")
    cleanup_text(text)
    series = []
    lines = list(text.stripped_strings)
    if lines and lines[0] == "Reprise du message précédent :":
        raise InvalidMessageError(err="skipping first message of new page (duplicate)")
    for line in lines:
        try:
            data = parse_line(line)
            logger.info(f"{BLUE}MATCH{RESET}: {data} ({line})")
            series.append(data.get("result"))
        except InvalidLineError as e:
            logger.info(f"{YELLOW}DISCARD{RESET}: {e} ({line})")

    if len(series) != 15:  # noqa:PLR2004
        raise InvalidMessageError(err=f"number of series must be 15, found {len(series)}")
    return {"user": user, "id": msg_id, "date": date, "results": tuple(series)}


def main() -> None:
    logging.basicConfig(format="%(message)s")
    args = parse_args()
    if not args.quiet:
        logger.setLevel(logging.INFO)

    entries = {}

    last_soup = fetch_soup(99999)  # number big enough to always be the last page
    last_page = get_last_page(last_soup)

    if args.start:
        start_page = args.start
        end_page = args.start + args.pages
    else:
        start_page = last_page - args.pages + 1
        end_page = last_page

    for page in range(start_page, end_page + 1):
        if page >= last_page:
            entries.update(get_messages(last_soup))
            break
        soup = fetch_soup(page)
        entries.update(get_messages(soup))

    logger.info("")
    logger.info(f"{WHITE}EXPORT{RESET}:")
    for i in entries:
        results = ",".join([f"{winner},{score}" for winner, score in entries[i]["results"]])
        print(f"{WHITE}{entries[i]['user']}{RESET},,{results}")  # noqa: T201


if __name__ == "__main__":
    main()
