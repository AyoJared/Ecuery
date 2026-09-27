# Ingest: real environmental data with verifiable provenance

The ETL workers from the stack table. They pull official data into Tiger (last `RECENT_DAYS`, default 7)
and Snowflake (2019 onward), and anchor every batch on Solana.

| Metric | History (Snowflake) | Recent (Tiger) |
| --- | --- | --- |
| PM2.5, ozone, NO2 | EPA AQS daily files (quality-assured), then EPA AirNow daily files for months AQS hasn't published yet | EPA AirNow hourly files |
| Temperature | NOAA NCEI GHCN-Daily (mean = (max+min)/2) | NOAA NWS airport observations |
| Humidity | NOAA NCEI GSOD dew point → relative humidity | NOAA NWS airport observations |
| CO2 (global) | NOAA GML Mauna Loa daily | NOAA GML Mauna Loa daily |
| Streamflow, water temperature | USGS NWIS daily means | USGS NWIS instantaneous values |

City → monitors/stations are defined in `shared/catalog.py`. No API keys are needed for any of these.

## Anywhere else in the world (on demand)

Places without local monitors are resolved by `shared/places.py` (Open-Meteo geocoding) and loaded the
first time someone asks (`ingest/on_demand.py`), from global **modeled** data:

| Metric | Source | Coverage |
| --- | --- | --- |
| PM2.5, ozone, NO2 | Copernicus CAMS | hourly; Europe from 2019, worldwide from Aug 2022 |
| Temperature, humidity | ECMWF ERA5 (history) + weather-model analysis (recent) | global |
| Streamflow | GloFAS (nearest modeled river) | global |

These are batches like any other: fingerprinted, anchored on Solana and labeled `quality = modeled`.
Coverage is tracked in the Tiger table `place_coverage`. After the first question, a place's history
tops up daily and its recent data hourly. A first question about a new place takes about 10–20 s.

If a Solana write fails (for example because of devnet rate limits), `python -m ingest.run --reanchor`
anchors those batches later.

## Natural disasters and weather events

`ingest/events.py` keeps events (records with a time, a place and details) in the Tiger table `events`.
It loads one source-year the first time a question needs it. Each load is a provenance batch anchored on
Solana, like the readings.

| Events | Source | Coverage |
| --- | --- | --- |
| Tornadoes (EF rating, path), hail, damaging wind, floods, hurricanes, winter storms, heat, drought | NOAA NCEI Storm Events Database (NWS-verified) | US, 1996 onward, published a few months behind |
| Earthquakes | USGS ComCat | worldwide, M2.5+ |
| Wildfires, severe storms, volcanoes, floods, landslides | NASA EONET | worldwide, notable events, 2017 onward |

Questions search around a place: its real extent from OpenStreetMap, widened for earthquakes and hurricanes.
US state and country searches also require the record to name that state or country. When nothing falls
inside the area, the answer names the nearest events.

## Run (from `backend/`)

```powershell
python -m ingest.run --recent     # refresh the last 7 days (run this hourly)
python -m ingest.run --history    # refresh 2019 -> 7 days ago (run daily or weekly)
python -m ingest.run --history --since 2025-01-01
```

After a big refresh, clear cached answers with `DELETE /ask/cache`.

## How provenance works

For each batch (one run of one source):

1. Every file downloaded from the agency is recorded with its URL and SHA-256.
2. The normalized rows are hashed (`rows_sha256`) and written to Tiger/Snowflake tagged with `batch_id`.
3. A manifest of source, dataset, quality, fetch time, file hashes, row hash and count is hashed and
   anchored on Solana as the memo `ecuery:src:v1:<manifest_sha256>`.
4. The manifest and its signature are stored in the Tiger table `ingest_batches`.

Answers from `/ask` list the batches their numbers came from (`provenance`). The answer's own Solana
record commits to those batches' manifest hashes.

## Checking a batch

- `GET /verify/batches` lists every batch, its quality and its Solana link.
- `GET /verify/batch/{id}` checks four things:
  - `manifest`: the registry copy still hashes to what was anchored.
  - `solana`: the chain memo equals that hash, signed by the backend wallet.
  - `rows`: the rows in the database still hash to what was ingested. An edit fails this check.
    Status is `superseded` when a newer ingest of the same source replaced some rows.
  - With `?refetch=true`, `source` re-downloads up to 3 of the agency files and compares bytes. Agencies
    revise data, and that shows up here instead of being hidden.
