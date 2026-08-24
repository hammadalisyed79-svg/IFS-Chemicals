"""Pakistan provinces and major cities — for master data location pickers."""

PROVINCES = [
    "Punjab",
    "Sindh",
    "Khyber Pakhtunkhwa",
    "Balochistan",
    "Islamabad Capital Territory",
    "Gilgit-Baltistan",
    "Azad Jammu & Kashmir",
]

PROVINCE_CITIES: dict[str, list[str]] = {
    "Punjab": [
        "Lahore", "Faisalabad", "Rawalpindi", "Gujranwala", "Multan", "Sialkot",
        "Sargodha", "Bahawalpur", "Sheikhupura", "Gujrat", "Jhelum", "Kasur",
        "Sahiwal", "Okara", "Pakpattan", "Khanewal", "Dera Ghazi Khan", "Muzaffargarh",
        "Rahim Yar Khan", "Vehari", "Attock", "Chiniot", "Hafizabad", "Mianwali",
        "Narowal", "Toba Tek Singh", "Wazirabad", "Burewala", "Kamoke", "Muridke",
    ],
    "Sindh": [
        "Karachi", "Hyderabad", "Sukkur", "Larkana", "Nawabshah", "Mirpur Khas",
        "Jacobabad", "Shikarpur", "Khairpur", "Dadu", "Badin", "Thatta", "Umerkot",
        "Ghotki", "Sanghar", "Matiari", "Tando Allahyar", "Tando Muhammad Khan",
    ],
    "Khyber Pakhtunkhwa": [
        "Peshawar", "Mardan", "Mingora", "Kohat", "Abbottabad", "Dera Ismail Khan",
        "Bannu", "Swabi", "Mansehra", "Charsadda", "Nowshera", "Haripur", "Timergara",
        "Tank", "Hangu", "Chitral",
    ],
    "Balochistan": [
        "Quetta", "Turbat", "Khuzdar", "Chaman", "Hub", "Gwadar", "Sibi", "Zhob",
        "Loralai", "Dera Murad Jamali", "Usta Muhammad", "Kalat",
    ],
    "Islamabad Capital Territory": ["Islamabad"],
    "Gilgit-Baltistan": ["Gilgit", "Skardu", "Hunza", "Ghizer", "Diamer"],
    "Azad Jammu & Kashmir": ["Muzaffarabad", "Mirpur", "Rawalakot", "Kotli", "Bhimber"],
}

_SELECT_PROVINCE = "— Select province —"
_SELECT_CITY = "— Select city —"
_OTHER_CITY = "— Other (type below) —"


def cities_for_province(province: str) -> list[str]:
    if not province or province == _SELECT_PROVINCE:
        return []
    return list(PROVINCE_CITIES.get(province, []))


def province_for_city(city: str | None) -> str | None:
    if not city or not str(city).strip():
        return None
    norm = str(city).strip().casefold()
    for prov, cities in PROVINCE_CITIES.items():
        if any(c.casefold() == norm for c in cities):
            return prov
    return None


def all_catalog_cities() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cities in PROVINCE_CITIES.values():
        for c in cities:
            k = c.casefold()
            if k not in seen:
                seen.add(k)
                out.append(c)
    return sorted(out, key=str.casefold)
