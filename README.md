# Turkey Administrative Geography Scraper

Python scripts that load Turkey’s administrative units (**il** / province, **ilçe** / district, **mahalle** / neighborhood) from the [TKGM CBS](https://cbsapi.tkgm.gov.tr) MEGSIS web API into a MySQL database.

Neighborhood records can include polygon geometry. A follow-up script fills missing coordinates for features that are not simple polygons (for example MultiPolygon).

# 👨‍💻 Author

**Arda Baran**

Computer Engineer

---


## Pipeline

Run the scripts in this order. Each step depends on data written by the previous one.

```text
1. il_scraper.py
      ↓  fills `iller`
2. ilce_scraper.py
      ↓  fills `ilceler` (keyed by province)
3. mahalle_scraper.py
      ↓  fills `mahalleler` (keyed by district, with Polygon rings)
4. mahalle_null_coordinates_fixer_for_non_polygon_areas.py
         backfills `coordinates` / `geo_type` where they are still NULL
```

| Script | Source API | Writes |
| --- | --- | --- |
| `il_scraper.py` | `maksIdariYapi/illiste` | `iller` |
| `ilce_scraper.py` | `maksIdariYapi/ilceliste/{il_id}` | `ilceler` |
| `mahalle_scraper.py` | `maksIdariYapi/mahalleliste/{ilce_id}` | `mahalleler`, `scraper_state` |
| `mahalle_null_coordinates_fixer_for_non_polygon_areas.py` | `maksIdariYapi/mahalleliste/{ilce_id}` | `mahalleler.coordinates`, `mahalleler.geo_type` |

## Requirements

- Python 3.9+
- MySQL / MariaDB (the scripts currently target a local [Laravel Sail](https://laravel.com/docs/sail) MySQL on port `3307`)
- Packages: `requests`, `pymysql`

```bash
pip install requests pymysql
```

## Database

Create a database (default name: `adres_data`) and tables matching the inserts below. IDs come from TKGM as UUID strings with braces stripped.

```sql
CREATE TABLE iller (
    id   CHAR(36)     NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE ilceler (
    id    CHAR(36)     NOT NULL PRIMARY KEY,
    name  VARCHAR(255) NOT NULL,
    il_id CHAR(36)     NOT NULL,
    CONSTRAINT fk_ilceler_il FOREIGN KEY (il_id) REFERENCES iller (id)
);

CREATE TABLE mahalleler (
    id          CHAR(36)     NOT NULL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    ilce_id     CHAR(36)     NOT NULL,
    polygon     LONGTEXT     NULL,   -- outer ring JSON from Polygon geometries
    coordinates LONGTEXT     NULL,   -- raw GeoJSON coordinates (any geometry type)
    geo_type    VARCHAR(64)  NULL,   -- e.g. Polygon, MultiPolygon
    CONSTRAINT fk_mahalleler_ilce FOREIGN KEY (ilce_id) REFERENCES ilceler (id)
);

CREATE TABLE scraper_state (
    name    VARCHAR(64)  NOT NULL PRIMARY KEY,
    last_id CHAR(36)     NULL
);

INSERT INTO scraper_state (name, last_id) VALUES ('mahalle', NULL);
```

`mahalle_scraper.py` reads and updates the `mahalle` row in `scraper_state`. Seed that row before the first neighborhood run.

## Configuration

Each script has its own connection block (`pymysql.connect(...)` or `DB_CONFIG`). Update host, port, user, password, and database to match your environment before running.

Default values in the repo match a typical Sail MySQL container (`localhost:3307`, database `adres_data`).

Rate limiting is hardcoded:

- Districts: `SLEEP_SECONDS = 0.3`
- Neighborhoods / fixer: `SLEEP_SECONDS = 3`

Keep those pauses so requests stay polite to the public API.

## Usage

```bash
python il_scraper.py
python ilce_scraper.py
python mahalle_scraper.py
python mahalle_null_coordinates_fixer_for_non_polygon_areas.py
```

### Resume behavior

`mahalle_scraper.py` is resumable. After each district it stores that district’s id in `scraper_state`. If the API call fails, the script stops; the next run skips already finished districts and restarts from the last stored id.

The coordinate fixer only processes districts that still have neighborhoods with `coordinates IS NULL`. You can rerun it until those rows are filled or the API fails (then rerun from the same query).

### What gets stored for geometry

- **Neighborhood scraper:** if the feature geometry is `Polygon`, the outer ring (`coordinates[0]`) is saved as JSON in `polygon`. Other geometry types leave `polygon` empty.
- **Fixer:** for rows with null `coordinates`, it stores the full `geometry.coordinates` JSON and `geometry.type` so MultiPolygon and similar shapes are not dropped.

Inserts use `ON DUPLICATE KEY UPDATE`, so rerunning a completed step refreshes names (and geometry fields) instead of duplicating rows.

## Notes

- The TKGM MEGSIS administrative API is a public GIS endpoint. Use it only for legitimate address / mapping data collection, respect their terms, and do not hammer the service.
- Credentials in the scripts are local development defaults. Do not commit production passwords.
- There is no `requirements.txt` yet; install `requests` and `pymysql` as shown above.
