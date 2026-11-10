"""What the model publishes for each spot, as plain data (dicts of lists and numbers).

Each product is a function that computes one piece and returns it; none of them write files
or know where the data goes (that's the publish step's job). Split by how often each piece
changes, so a scheduled job only redoes what changed:

  spot_map.spot_map()            coastline, depth bands, map views     once per spot (tables change)
  spot_now.spot_now()            current swells, their paths, surf     every buoy reading (hourly)
  spot_lineup.spot_lineup()      the "In the water" wave field         with spot_now
  spot_forecast.spot_forecast()  7-day surf and swell series           every forecast run (6-hourly)

page.page_data() assembles them into the single object the current HTML page reads.
The same pieces are what the website (and later a mobile app) will fetch as separate files.
"""
SCHEMA_VERSION = 1
