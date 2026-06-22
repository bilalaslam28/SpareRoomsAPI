import requests


def get_travel_information(start_coords, api_key=None, work_coords=None):
    """
    Get minimum transit travel time from start_coords to one or more work destinations
    using the free TfL Journey Planner API. api_key is unused but kept for compatibility.
    work_coords can be a single (lat, lon) tuple or a list of tuples.
    """
    if start_coords is None:
        return {'transit_time_minutes': None, 'bike_time_minutes': None}

    destinations = work_coords if isinstance(work_coords, list) else [work_coords]

    min_time = None
    for dest in destinations:
        t = _tfl_journey_minutes(start_coords, dest)
        if t is not None and (min_time is None or t < min_time):
            min_time = t

    return {'transit_time_minutes': min_time, 'bike_time_minutes': None}


def _tfl_journey_minutes(start, end):
    from_str = f"{start[0]},{start[1]}"
    to_str = f"{end[0]},{end[1]}"
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{from_str}/to/{to_str}"
    try:
        r = requests.get(url, params={'journeyPreference': 'leasttime'}, timeout=15)
        journeys = r.json().get('journeys', [])
        if journeys:
            return min(j['duration'] for j in journeys)
        return None
    except Exception as e:
        print(f"[!] TfL API error: {e}")
        return None
