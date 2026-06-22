from src.spareroom import SpareRoom, read_existing_rooms_from_spreadsheet, append_new_rooms_to_spreadsheet

filename = 'spareroom_listing.csv'

# -- Search configuration --
# £650/month ≈ £150/week
search_url = (
    '/search.pl?action=search&flatshare_type=offered'
    '&search=London&min_rent=%i&max_rent=%i&per=pw'
    '&min_term=0&max_term=0&showme_rooms=Y'
)
min_rent_pw = 0
max_rent_pw = 150

# Moorgate and Old Street stations (lat, lon)
WORK_COORDS = [
    (51.5186, -0.0886),  # Moorgate
    (51.5263, -0.0876),  # Old Street
]

API_KEY = None  # Using TfL API — no key required
entries_to_scrape = 100

# -- Filter criteria --
MAX_COMMUTE_MINUTES = 35
ACCEPTED_ROOM_TYPES = ['single', 'double']
# ------------------------------------------


def _room_has_valid_type(room):
    for i in range(5):
        attr = f'room_{i}_type'
        if hasattr(room, attr):
            rt = (getattr(room, attr) or '').lower()
            if any(t in rt for t in ACCEPTED_ROOM_TYPES):
                return True
    return False


def _room_is_within_commute(room):
    return (
        hasattr(room, 'transit_time')
        and room.transit_time is not None
        and room.transit_time <= MAX_COMMUTE_MINUTES
    )


def main():
    existing_rooms_df = read_existing_rooms_from_spreadsheet(filename)

    spare_room = SpareRoom(search_url, WORK_COORDS, API_KEY, min_rent_pw, max_rent_pw, entries_to_scrape)
    new_rooms = spare_room.get_rooms(previous_rooms=existing_rooms_df)

    filtered_new_rooms = []
    for room in new_rooms:
        already_seen = (
            not existing_rooms_df.empty
            and room.id in existing_rooms_df['id'].values
        )
        if not already_seen and _room_is_within_commute(room) and _room_has_valid_type(room):
            filtered_new_rooms.append(room)

    append_new_rooms_to_spreadsheet(existing_rooms_df, filtered_new_rooms, filename)
    print(f'[+] {len(filtered_new_rooms)} matching rooms saved to ./{filename}')


if __name__ == "__main__":
    main()
