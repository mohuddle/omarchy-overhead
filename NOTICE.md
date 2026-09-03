# Notices

## ADS-B data

Live positions come from public ADS-B feeder networks that speak the same
readsb / ADS-B Exchange v2 JSON used by [globe.adsbexchange.com](https://globe.adsbexchange.com/):

- [adsb.fi](https://opendata.adsb.fi/) open data API
- [adsb.lol](https://adsb.lol/) public API
- [The OpenSky Network](https://opensky-network.org/) as a last-resort fallback

ADS-B Exchange's own REST gateway is keyed and is not called. This project
does not scrape the globe site.

Please treat the feeds gently (this watcher polls about once every 12 seconds)
and consider running a receiver if you use the data regularly.

## Cessna icon

The bar glyph is the Cessna silhouette published at
[adsb-radar.com/help/icons/cessna.svg](https://adsb-radar.com/help/icons/cessna.svg).
It is recolored to the active Omarchy theme.

## Location

Device location is requested only after you press **Allow**, via the desktop
portal or GeoClue. There is no IP geolocation fallback. Manual coordinates
and place names (OpenStreetMap Nominatim) never require that permission.
Coordinates are stored under `~/.local/state/omarchy/overhead/` and are sent
only as a lat/lon radius query to the ADS-B APIs above.
