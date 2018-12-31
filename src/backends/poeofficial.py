import requests
import concurrent.futures
import urllib
from ratelimit import limits, sleep_and_retry
from src import constants
from src import flip


def name():
    return "Path of Exile Offical Trade API"


def fetch_offers(league, currency_pairs, limit=3):
    params = [[league, pair[0], pair[1], limit] for pair in currency_pairs]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = executor.map(lambda p: fetch_offers_for_pair(*p), params)
        offers = list(map(lambda x: x, futures))
        # Filter offers from currency pairs that do not hold any offers
        offers = [x for x in offers if len(x["offers"]) > 0]
        return offers


"""
Private helpers below
"""


def fetch_offers_for_pair(league, want, have, limit=5):
    """
    The official rate-limit is 5:5:60 -> stay right under it with 4:5
    """
    offer_ids, query_id = fetch_offers_ids(league, want, have)
    offers = fetch_offers_details(offer_ids, query_id, limit)
    viable_offers = flip.filter_viable_offers(want, have, offers)

    return {
        "offers": viable_offers,
        "want": want,
        "have": have,
        "league": league
    }


class RateLimitException(Exception):
    pass


@sleep_and_retry
@limits(calls=4, period=5)
def fetch_offers_ids(league, want, have):
    url = "http://www.pathofexile.com/api/trade/exchange/{}".format(
        urllib.parse.quote(league))
    payload = {
        "exchange": {
            "status": {
                "option": "online"
            },
            "have": [map_currency(have)],
            "want": [map_currency(want)]
        }
    }
    r = requests.post(url, json=payload)
    json = r.json()

    try:
        offer_ids = json["result"]
        query_id = json["id"]
        return offer_ids, query_id
    except KeyError:
        raise RateLimitException("Reached rate-limit when fetching offer ids")


@sleep_and_retry
@limits(calls=4, period=5)
def fetch_offers_details(offer_ids, query_id, limit=5):

    if len(offer_ids) is 0:
        return []

    id_string = ",".join(offer_ids[:limit])
    url = "http://www.pathofexile.com/api/trade/fetch/{}?query={}&exchange".format(
        id_string, query_id)
    r = requests.get(url)
    try:
        result = r.json()["result"]
        offers = [map_offers_details(x) for x in result]
        return offers
    except KeyError:
        raise Exception("Reached rate-limit when feting offer details")


def map_offers_details(offer_details):
    contact_ign = offer_details["listing"]["account"]["lastCharacterName"]
    stock = offer_details["listing"]["price"]["item"]["stock"]
    receive = offer_details["listing"]["price"]["item"]["amount"]
    pay = offer_details["listing"]["price"]["exchange"]["amount"]
    conversion_rate = round(receive/pay, 4)

    return {
        "contact_ign": contact_ign,
        "conversion_rate": conversion_rate,
        "stock": stock
    }


def map_currency(currency):
    if currency in constants.currencies:
        return constants.currencies[currency]["poeofficial"]
    else:
        raise Exception("Unknown currency key")
