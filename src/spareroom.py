import time
import requests
from .distance_calcaulation import get_travel_information
from bs4 import BeautifulSoup
import pandas as pd
import datetime

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


class SpareRoom:
    DOMAIN = 'https://www.spareroom.co.uk'
    URL_ROOMS = DOMAIN + '/flatshare'

    def __init__(self, search_url, workplace_coords, citymapper_api_key, min_price_pw=180, max_price_pw=290, entries_to_scrape=30):
        self.workplace_coords = workplace_coords
        self.citymapper_api_key = citymapper_api_key
        self.URL_SEARCH = self.URL_ROOMS + search_url
        self.entries_to_scrape = entries_to_scrape

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        r = self.session.get(self.URL_SEARCH % (min_price_pw, max_price_pw))
        s = BeautifulSoup(r.content, 'lxml')
        self.url = r.url + 'offset=%i'

        nav = s.find("p", {"class": "navcurrent"})
        if nav:
            self.pages = int(int(nav.findAll("strong")[1].string[:-1]) / 10)
        else:
            self.pages = 1
            print('[!] Could not parse pagination — defaulting to 1 page')

    def _get_soup(self, url):
        r = self.session.get(url, allow_redirects=False)
        if r.status_code == 200:
            return BeautifulSoup(r.content, 'lxml')
        elif r.status_code in (301, 302):
            print('Finalizado')
            exit(0)
        else:
            print('[X] Response %s. Something went wrong.' % r.status_code)
            exit(1)

    def _get_rooms_info(self, rooms_soup, previous_rooms=None):
        rooms = list()
        try:
            for article in rooms_soup.find_all('article'):
                add_room = True
                if previous_rooms is not None and not previous_rooms.empty:
                    room_id = int(article.find("a")['href'].split("flatshare_id=")[1].split("&")[0])
                    add_room = room_id not in previous_rooms['id'].values

                if add_room:
                    room = Room(article, self.DOMAIN, self.workplace_coords, self.citymapper_api_key, self.session)
                    if getattr(room, '_initialized', False):
                        rooms.append(room)
                    else:
                        print('[X] Room skipped (listing page blocked or not live)')
                else:
                    print('[X] Room already exists')
        except Exception as e:
            print("Catch exception: ", e)
        return rooms

    def get_rooms(self, previous_rooms=None):
        rooms = list()
        for i in range(0, self.entries_to_scrape, 10):
            print('[ ] Offset: %i \t Rooms so far: %i' % (i, len(rooms)))
            soup = self._get_soup(self.url % i)
            rooms.extend(self._get_rooms_info(soup, previous_rooms=previous_rooms))
            time.sleep(1)
        return rooms


class Room:
    def __init__(self, room_soup, domain, workplace_coords, citymapper_api_key, session=None):
        self._initialized = False
        fetch = session.get if session else requests.get

        self.url = str(domain + room_soup.find("a")['href'])
        self.id = int(self.url.split("flatshare_id=")[1].split("&")[0])

        r = fetch(self.url)
        if r.status_code != 200:
            print(f'[X] Listing returned {r.status_code}: {self.url}')
            return
        room_soup = BeautifulSoup(r.content, 'lxml')

        try:
            header = room_soup.find("div", {"id": "listing_heading"})
            self.title = str(header.h1.text.strip()) if header.h1 else None
        except AttributeError:
            print('[X] Error parsing listing page - probably not live')
            return

        try:
            self.desc = str(room_soup.find("p", {"class": "detaildesc"}).text.strip().replace('\r\n', ' '))
        except AttributeError:
            self.desc = None

        key_features = self._get_key_features(room_soup)
        [setattr(self, feature, key_features[feature]) for feature in key_features]

        pm_prices = self._get_pm_price(room_soup)
        for i, room in enumerate(pm_prices):
            setattr(self, f'room_{i}_price', room['price'])
            setattr(self, f'room_{i}_type', room['type'])

        self.location_coords = self._get_location_coords(room_soup)
        commute_times = get_travel_information(self.location_coords, api_key=citymapper_api_key, work_coords=workplace_coords)
        self.cycle_time = commute_times['bike_time_minutes']
        self.transit_time = commute_times['transit_time_minutes']

        features = self._get_features(room_soup)
        [setattr(self, feature, features[feature]) for feature in features]

        self.date_scraped = datetime.datetime.now().strftime("%d-%m-%Y")
        self._initialized = True

    def __str__(self):
        return str(self.__dict__)

    def _get_pm_price(self, room_soup):
        rooms = []
        room_price_lists = room_soup.find('ul', class_='room-list')
        if not room_price_lists:
            return rooms
        for li in room_price_lists.find_all('li'):
            try:
                price = li.find('strong', {"class": "room-list__price"}).text.strip()
                price, interval = price.split(" ")
                price = price.replace("£", "")
                if interval == "pw":
                    price = int(price) * (52 / 12)
                type_ = li.find('small').text.strip().replace('(', '').replace(')', '')
                rooms.append({'price': price, 'type': type_})
            except Exception:
                continue
        return rooms

    def _get_key_features(self, room_soup):
        features = {'Type': None, 'Area': None, 'Postcode': None, 'Nearest station': None}
        feature_list = room_soup.find('ul', class_='key-features')
        if not feature_list:
            return features
        for i, li in enumerate(feature_list.find_all('li')):
            if i >= len(features):
                break
            text = li.text.strip()
            if i == 2:
                text = text.split(" ")[0]
            elif i == 3:
                text = text.split("\n")[0]
            features[list(features.keys())[i]] = text
        return features

    def _get_features(self, room_soup):
        features = {}
        for feature_list in room_soup.findAll('dl', class_='feature-list'):
            for dt, dd in zip(feature_list.find_all('dt'), feature_list.find_all('dd')):
                key = dt.text.replace('\n', ' ').replace('#', '').strip().capitalize()
                features[key] = dd.text.strip()
        return features

    def _get_location_coords(self, room_soup):
        if not room_soup.head:
            return None
        for script in room_soup.head.findAll("script"):
            text = script.text
            if "_sr.page" in text:
                idx = text.find("location")
                if idx == -1:
                    continue
                try:
                    location = text[idx:idx+100].split('{')[1].split('}')[0]
                    parts = location.split(',')[:-1]
                    coords = [float(p.split(':')[1].strip().replace('"', '')) for p in parts]
                    return (coords[0], coords[1])
                except Exception:
                    continue
        return None


def read_existing_rooms_from_spreadsheet(file_path):
    try:
        df = pd.read_csv(file_path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        print("Creating new spreadsheet for rooms.")
        df = pd.DataFrame()
    return df


def append_new_rooms_to_spreadsheet(df, new_rooms, file_path):
    new_df = pd.DataFrame([
        {k: v for k, v in room.__dict__.items() if k != '_initialized'}
        for room in new_rooms
    ])
    combined_df = pd.concat([df, new_df], ignore_index=True)

    def reorder_columns(columns):
        room_columns = [col for col in columns if col.startswith("room_")]
        deposit_columns = [col for col in columns if col.startswith("Deposit")]
        non_room_columns = [col for col in columns if col not in room_columns + deposit_columns]

        room_and_deposit = [
            room_columns[i * 2:i * 2 + 2] + [deposit_columns[i]]
            for i in range(len(deposit_columns))
        ]
        room_and_deposit = [item for sublist in room_and_deposit for item in sublist]

        reordered = []
        for col in non_room_columns:
            reordered.append(col)
            if col.startswith("Maximum term"):
                reordered.extend(room_and_deposit)
        return reordered

    try:
        reordered = reorder_columns(combined_df.columns)
        combined_df = combined_df[reordered]
    except Exception:
        pass

    combined_df.to_csv(file_path, index=False)
