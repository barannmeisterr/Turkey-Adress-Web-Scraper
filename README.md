# 🗺️ Turkey Administrative Geography Scraper

### Python-Based Geographic Data Collection & PostgreSQL/PostGIS Integration

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-Spatial_Database-008B8B)
![QGIS](https://img.shields.io/badge/QGIS-Geospatial_Analysis-589632?logo=qgis&logoColor=white)
![Status](https://img.shields.io/badge/Status-Research_Project-orange)

---

## 👨‍💻 Author

**Arda Baran**

Computer Engineer


---

## 📌 Overview

**Turkey Administrative Geography Scraper** is a Python-based geographic
data collection pipeline designed to retrieve, process, and store
administrative boundaries, road networks, and address-related building
points from Türkiye's General Directorate of Land Registry and Cadastre
(TKGM) MEGSİS web services.

The project focuses on collecting large-scale geographic datasets and
organizing them in a PostgreSQL database with PostGIS support.

Initially developed for **Antalya, Türkiye**, the system provides a
geospatial data foundation for:

- Geographic Information Systems (GIS)
- Wireless Internet Service Provider (WISP) infrastructure planning
- Point of Presence (POP) discovery
- Spatial database research
- Address-based geographic analysis
- Regional infrastructure assessment

---

## ✨ Key Features

### 🌍 Hierarchical Geographic Data Collection

Retrieves geographic information through Türkiye's administrative
hierarchy:

- Provinces (İl)
- Districts (İlçe)
- Neighborhoods (Mahalle)
- Streets and roads (Yol)
- Address-related building points (Numarataj)

### 🗄️ PostgreSQL & PostGIS Integration

- Structured relational data storage
- Geographic geometry management
- Spatial indexing with GiST
- Administrative relationship mapping
- SQL-based geographic analysis
- Direct integration with QGIS

### 🔄 Resumable Data Collection

The scraper maintains persistent progress information, allowing
interrupted collection operations to continue without restarting
the entire process.

### 🛡️ Error Handling & Retry Mechanism

- Automatic retry attempts
- Connection failure handling
- Request timeout management
- Configurable request delays
- Collection status tracking

### 📊 Large-Scale Data Processing

Designed to process hundreds of thousands of geographic records
while maintaining structured database relationships.

---

## 🏗️ System Architecture

```text
                  +----------------------+
                  |    TKGM MEGSİS API   |
                  +----------+-----------+
                             |
                             v
                  +----------------------+
                  |   Python Scraper     |
                  |                      |
                  | - HTTP Requests      |
                  | - JSON Processing    |
                  | - Retry Mechanism    |
                  | - Progress Tracking  |
                  +----------+-----------+
                             |
                             v
                  +----------------------+
                  |    PostgreSQL 18     |
                  |       PostGIS        |
                  +----------+-----------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
    +-------------------+         +-------------------+
    |       QGIS        |         |    WISP Planner   |
    |                   |         |                   |
    | Spatial Analysis  |         | POP Discovery     |
    | Visualization     |         | Coverage Planning |
    +-------------------+         +-------------------+
```

---

## 📂 Geographic Data Hierarchy

The scraper processes administrative and geographic entities
in a hierarchical structure.

```text
Türkiye
│
└── Province
    │
    └── District
        │
        └── Neighborhood
            │
            └── Street / Road
                │
                └── Address / Building Point
```

This structure enables geographic filtering, relational queries,
and administrative data organization.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|------------|---------|
| Python | Data collection and processing |
| REST APIs | Geographic data retrieval |
| JSON / GeoJSON | Geographic data representation |
| PostgreSQL 18 | Relational database management |
| PostGIS | Spatial database functionality |
| SQL | Data processing and querying |
| QGIS | Geographic visualization and analysis |
| GiST Indexes | Spatial query optimization |

---

## 🗄️ Database Structure

The PostgreSQL database contains the following primary tables:

| Table | Description |
|-------|-------------|
| `iller` | Province boundaries and geographic metadata |
| `ilceler` | District boundaries and province relationships |
| `mahalleler` | Neighborhood boundaries and district relationships |
| `yollar` | Street and road information |
| `binalar` | Address-related building points |
| `yol_scraper_state` | Road collection progress |
| `bina_scraper_state` | Building/address collection progress |

### Coordinate Reference System

Geographic geometries are stored using:

```text
EPSG:4326 — WGS 84
```

### Spatial Indexing

PostGIS GiST indexes support efficient geographic queries.

```sql
CREATE INDEX IF NOT EXISTS idx_binalar_geometry
ON public.binalar
USING GIST (geometry);
```

Spatial indexing is particularly useful for:

- Proximity searches
- Geographic filtering
- Spatial joins
- Point-in-polygon operations
- Infrastructure planning queries

---

## 🔄 Data Collection Workflow

The scraper follows a hierarchical collection pipeline.

```text
START
  |
  v
Retrieve Province Information
  |
  v
Retrieve Districts
  |
  v
Retrieve Neighborhoods
  |
  v
Retrieve Streets / Roads
  |
  v
Retrieve Building Points
  |
  v
Parse JSON / Geometry
  |
  v
Insert Data into PostgreSQL
  |
  v
Update Scraping State
  |
  v
COMPLETE
```

### Request Processing

Each collection operation follows these steps:

1. Load pending geographic entities.
2. Send an HTTP request to the source API.
3. Validate and parse the response.
4. Extract geographic identifiers and geometry.
5. Store the processed records in PostgreSQL.
6. Update the corresponding collection state.
7. Continue with the next entity.

---

## 🔁 Resumable Scraping

Large-scale geographic data collection may be interrupted by:

- Network connection failures
- API response errors
- Request timeouts
- Temporary service unavailability
- Application shutdowns

The project uses persistent state tables to track collection
progress.

### State Tables

```sql
SELECT *
FROM public.yol_scraper_state;
```

```sql
SELECT *
FROM public.bina_scraper_state;
```

These tables allow the collection process to identify completed,
pending, and failed operations.

### Retry Configuration

The scraper supports configurable retry and request-delay
parameters.

Example configuration values:

```python
MAX_RETRIES = 3
REQUEST_DELAY = 2.0
REPORT_INTERVAL = 100
```

These values are illustrative and should be adjusted according
to the source service's access policies and operational limits.

---

## 📊 Dataset Statistics

The Antalya data collection project has processed a substantial
volume of geographic information.

| Geographic Entity | Approximate Records |
|-------------------|--------------------:|
| Province | 1 |
| District | 19 |
| Neighborhoods | 900+ |
| Road-related records | 42,000+ |
| Building-related points | 1,112,000+ |

> **Note:** Address-point records do not necessarily represent
> unique physical buildings. Duplicate identifiers and administrative
> associations should be validated before interpreting these
> records as building counts.

The statistics represent a project collection snapshot rather
than official or continuously updated government statistics.

---

## 🧭 Spatial Query Examples

### 1. Find Address Points Within a 1 km Radius

```sql
SELECT
    b.id,
    b.name,
    ROUND(
        ST_Distance(
            b.geometry::geography,
            ST_SetSRID(
                ST_MakePoint(30.571703, 37.1212036),
                4326
            )::geography
        )::numeric,
        2
    ) AS distance_meters
FROM public.binalar b
WHERE ST_DWithin(
    b.geometry::geography,
    ST_SetSRID(
        ST_MakePoint(30.571703, 37.1212036),
        4326
    )::geography,
    1000
);
```

### 2. Count Distinct Address Identifiers by Neighborhood

```sql
SELECT
    m.name AS neighborhood,
    COUNT(DISTINCT b.id) AS address_count
FROM public.mahalleler m
LEFT JOIN public.binalar b
    ON ST_Covers(
        m.geometry,
        b.geometry
    )
GROUP BY
    m.id,
    m.name
ORDER BY address_count DESC;
```

### 3. Find Streets in a Selected Neighborhood

```sql
SELECT
    y.id,
    y.name AS street_name
FROM public.yollar y
JOIN public.mahalleler m
    ON y.mahalle_id = m.id
WHERE m.name = 'Uncalı'
ORDER BY y.name;
```

### 4. Calculate Distance Between Geographic Points

```sql
SELECT
    ROUND(
        ST_Distance(
            ST_SetSRID(
                ST_MakePoint(30.571703, 37.1212036),
                4326
            )::geography,
            ST_SetSRID(
                ST_MakePoint(30.600000, 37.130000),
                4326
            )::geography
        )::numeric,
        2
    ) AS distance_meters;
```

---

## 🗺️ QGIS Integration

The collected geographic data can be visualized directly
in QGIS using a PostgreSQL/PostGIS connection.

### Supported GIS Operations

- Administrative boundary visualization
- Street and road mapping
- Address-point visualization
- Spatial filtering
- Geographic density analysis
- Point-in-polygon queries
- Infrastructure planning
- Geographic data validation

### Connection Information

```text
Database Type : PostgreSQL
Database Name : wisp_planner
Host          : localhost
Port          : 5432
CRS           : EPSG:4326
```

Database credentials must be configured locally and should
never be committed to a public repository.

---

## 📡 Use Cases

### Wireless Infrastructure Planning

The collected geographic information can support:

- Potential POP location discovery
- Address density analysis
- Regional network expansion research
- Candidate site identification
- Geographic coverage assessment
- Infrastructure feasibility studies

### GIS Applications

- Administrative boundary analysis
- Road network visualization
- Spatial database research
- Geographic data enrichment
- Regional geographic statistics

### Location-Based Applications

- Address lookup systems
- Geographic search applications
- Infrastructure availability research
- Location intelligence platforms

---

## ⚡ Performance Considerations

Large geographic datasets require efficient database
operations and query optimization.

Recommended techniques include:

- GiST spatial indexes
- B-tree indexes on relational identifiers
- Batch processing where appropriate
- Incremental collection
- Persistent progress tracking
- Query execution plan analysis
- Spatial filtering before expensive calculations

PostgreSQL provides query analysis tools such as:

```sql
EXPLAIN ANALYZE
SELECT COUNT(*)
FROM public.binalar;
```

---

## 🔍 Data Quality Considerations

Geographic data obtained from external services may contain
incomplete or inconsistent relationships.

Important validation checks include:

- Duplicate geographic identifiers
- Missing geometry
- Invalid geographic coordinates
- Administrative boundary inconsistencies
- Incorrect neighborhood associations
- Repeated address points
- Incomplete API responses

Spatial relationships should be validated using PostGIS
functions when administrative identifiers are insufficient.

---

## 🚀 Future Improvements

Potential future development areas:

- [ ] Asynchronous HTTP request processing
- [ ] Adaptive request scheduling
- [ ] Advanced duplicate detection
- [ ] Automated spatial validation
- [ ] Incremental data synchronization
- [ ] Data quality monitoring
- [ ] Docker-based deployment
- [ ] GIS export automation
- [ ] REST API for collected geographic data
- [ ] Integration with additional open geospatial datasets

---

## ⚠️ Disclaimer

This project is an independent software engineering and
geospatial research initiative.

It is not affiliated with, sponsored by, or officially
endorsed by the Turkish General Directorate of Land Registry
and Cadastre (TKGM).

Access to source services and use of geographic data are
subject to applicable terms, licensing requirements,
rate limits, and legal restrictions.

The project does not guarantee the completeness, accuracy,
or official validity of collected geographic information.

---



⭐ If you find this project useful, consider starring the repository.

**Built with Python, PostgreSQL, and PostGIS.**
