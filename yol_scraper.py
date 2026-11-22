
import os
import json
import uuid
import time
import random

import requests
import psycopg

from psycopg.types.json import Jsonb


# ==========================================
# VERİTABANI AYARLARI
# ==========================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "wisp_planner",
    "user": "postgres",
    "password": os.environ["PGPASSWORD"]
}

ANTALYA_ID = uuid.UUID(
    "C9F49F91-EC26-4570-9C23-B5A431FD12C6"
)

BASE_URL = (
    "https://cbsapi.tkgm.gov.tr/"
    "megsiswebapi.v3.1/api/"
    "maksIdariYapi/numaratajliste"
)

REQUEST_DELAY = 2
MAX_RETRIES = 3

# None: bütün yollar
# 10: sadece 10 benzersiz yol
MAX_ROADS = 10


# ==========================================
# 1. YOLLARI VERİTABANINDAN GETİR
# ==========================================

def get_pending_yollar(conn):

    sql = """
        SELECT
            y.id,
            MIN(y.name) AS yol_name,
            STRING_AGG(
                DISTINCT i.name,
                ', '
            ) AS ilce_name

        FROM yollar y

        INNER JOIN mahalleler m
            ON y.mahalle_id = m.id

        INNER JOIN ilceler i
            ON m.ilce_id = i.id

        LEFT JOIN bina_scraper_state s
            ON y.id = s.yol_id
           AND y.mahalle_id = s.mahalle_id

        WHERE i.il_id = %s

        GROUP BY y.id

        HAVING COUNT(*) FILTER (
            WHERE s.yol_id IS NULL
               OR s.status != 'completed'
        ) > 0

        ORDER BY y.id
    """

    params = [ANTALYA_ID]

    if MAX_ROADS is not None:
        sql += " LIMIT %s"
        params.append(MAX_ROADS)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ==========================================
# 2. YOLUN MAHALLE İLİŞKİLERİNİ GETİR
# ==========================================

def get_pending_mahalle_ids(conn, yol_id):

    sql = """
        SELECT y.mahalle_id

        FROM yollar y

        INNER JOIN mahalleler m
            ON y.mahalle_id = m.id

        INNER JOIN ilceler i
            ON m.ilce_id = i.id

        LEFT JOIN bina_scraper_state s
            ON y.id = s.yol_id
           AND y.mahalle_id = s.mahalle_id

        WHERE y.id = %s
          AND i.il_id = %s
          AND (
              s.yol_id IS NULL
              OR s.status != 'completed'
          )

        ORDER BY y.mahalle_id
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (yol_id, ANTALYA_ID)
        )

        return [
            row[0]
            for row in cur.fetchall()
        ]


# ==========================================
# 3. TKGM API'DEN NUMARATAJ ÇEK
# ==========================================

def fetch_binalar(session, yol_id):

    yol_uuid = str(yol_id).upper()

    url = f"{BASE_URL}/%7B{yol_uuid}%7D"

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                timeout=(15, 60)
            )

            # Erişim engeli / rate limit
            if response.status_code in (403, 429):

                raise RuntimeError(
                    f"API erişimi sınırlandırdı: "
                    f"HTTP {response.status_code}"
                )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):

                raise ValueError(
                    "API geçersiz JSON döndürdü."
                )

            features = data.get("features")

            if not isinstance(features, list):

                raise ValueError(
                    "API yanıtında features listesi yok."
                )

            # ÖNEMLİ:
            # Bazı yollarda numarataj olmayabilir.
            # Boş features geçerli sonuçtur.
            return features

        except RuntimeError:
            # 403 / 429 durumunda dur.
            raise

        except requests.HTTPError as exc:

            status = response.status_code

            # Kalıcı HTTP hatalarını tekrar deneme.
            if status not in (500, 502, 503, 504):
                raise

            if attempt == MAX_RETRIES:
                raise

            print(
                f"  Sunucu hatası: {exc}"
            )

        except (
            requests.ConnectionError,
            requests.Timeout
        ) as exc:

            if attempt == MAX_RETRIES:
                raise

            print(
                f"  Bağlantı hatası: {exc}"
            )

        except ValueError:
            # Hatalı JSON'u yeniden deneyerek
            # sunucuya yük bindirmiyoruz.
            raise

        wait = min(
            30,
            2 ** attempt + random.uniform(0, 1)
        )

        print(
            f"  {wait:.1f} saniye sonra "
            f"tekrar denenecek..."
        )

        time.sleep(wait)


# ==========================================
# 4. BİNA VERİLERİNİ DOĞRULA
# ==========================================

def prepare_binalar(yol_id, mahalle_ids, features):

    prepared = []

    seen = set()

    for feature in features:

        if not isinstance(feature, dict):

            raise ValueError(
                "Feature nesnesi geçersiz."
            )

        props = feature.get("properties")
        geometry = feature.get("geometry")

        if not isinstance(props, dict):

            raise ValueError(
                "Bina properties alanı geçersiz."
            )

        if not isinstance(geometry, dict):

            raise ValueError(
                "Bina geometry alanı geçersiz."
            )

        if geometry.get("type") != "Point":

            raise ValueError(
                "Beklenmeyen geometri türü: "
                f"{geometry.get('type')}"
            )

        coordinates = geometry.get("coordinates")

        if (
            not isinstance(coordinates, list)
            or len(coordinates) != 2
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                for value in coordinates
            )
        ):

            raise ValueError(
                "Bina koordinatları geçersiz."
            )

        raw_id = props.get("id")
        name = props.get("text")

        if not raw_id or not isinstance(name, str):

            raise ValueError(
                "Bina ID veya adı eksik."
            )

        bina_id = uuid.UUID(
            str(raw_id).strip("{}")
        )

        name = name.strip()

        if len(name) > 300:

            raise ValueError(
                "Bina adı 300 karakterden uzun."
            )

        geometry_json = json.dumps(
            geometry,
            ensure_ascii=False
        )

        for mahalle_id in mahalle_ids:

            key = (
                bina_id,
                yol_id,
                mahalle_id
            )

            if key in seen:
                continue

            seen.add(key)

            prepared.append((
                bina_id,
                yol_id,
                mahalle_id,
                name,
                geometry_json,
                Jsonb(props),
                Jsonb(geometry)
            ))

    return prepared


# ==========================================
# 5. BİNALARI POSTGRESQL'E KAYDET
# ==========================================

def save_binalar(
    conn,
    yol_id,
    mahalle_ids,
    features
):

    prepared = prepare_binalar(
        yol_id,
        mahalle_ids,
        features
    )

    insert_sql = """
        INSERT INTO binalar (
            id,
            yol_id,
            mahalle_id,
            name,
            geometry,
            properties,
            raw_geometry
        )

        VALUES (
            %s,
            %s,
            %s,
            %s,
            ST_SetSRID(
                ST_GeomFromGeoJSON(%s),
                4326
            ),
            %s,
            %s
        )

        ON CONFLICT (
            id,
            yol_id,
            mahalle_id
        )

        DO UPDATE SET
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            properties = EXCLUDED.properties,
            raw_geometry = EXCLUDED.raw_geometry,
            updated_at = NOW()
    """

    state_sql = """
        INSERT INTO bina_scraper_state (
            yol_id,
            mahalle_id,
            status,
            attempt_count,
            building_count,
            last_error,
            completed_at,
            updated_at
        )

        VALUES (
            %s,
            %s,
            'completed',
            1,
            %s,
            NULL,
            NOW(),
            NOW()
        )

        ON CONFLICT (yol_id, mahalle_id)

        DO UPDATE SET
            status = 'completed',
            attempt_count =
                bina_scraper_state.attempt_count + 1,
            building_count = EXCLUDED.building_count,
            last_error = NULL,
            completed_at = NOW(),
            updated_at = NOW()
    """

    # Bina kayıtları ve tamamlanma durumu
    # aynı transaction içerisinde kaydedilir.
    with conn.transaction():

        with conn.cursor() as cur:

            for row in prepared:
                cur.execute(insert_sql, row)

            # Her mahalle için kaydedilen
            # benzersiz numarataj sayısı.
            count_per_mahalle = (
                len(prepared) // len(mahalle_ids)
                if mahalle_ids else 0
            )

            for mahalle_id in mahalle_ids:

                cur.execute(
                    state_sql,
                    (
                        yol_id,
                        mahalle_id,
                        count_per_mahalle
                    )
                )

    return len(prepared)


# ==========================================
# 6. HATALI YOLU KAYDET
# ==========================================

def mark_failed(conn, yol_id, mahalle_ids, error):

    sql = """
        INSERT INTO bina_scraper_state (
            yol_id,
            mahalle_id,
            status,
            attempt_count,
            last_error,
            updated_at
        )

        VALUES (
            %s,
            %s,
            'failed',
            1,
            %s,
            NOW()
        )

        ON CONFLICT (yol_id, mahalle_id)

        DO UPDATE SET
            status = 'failed',
            attempt_count =
                bina_scraper_state.attempt_count + 1,
            last_error = EXCLUDED.last_error,
            updated_at = NOW()

        WHERE bina_scraper_state.status
            IS DISTINCT FROM 'completed'
    """

    with conn.transaction():

        with conn.cursor() as cur:

            for mahalle_id in mahalle_ids:

                cur.execute(
                    sql,
                    (
                        yol_id,
                        mahalle_id,
                        str(error)[:4000]
                    )
                )


# ==========================================
# 7. İLERLEME RAPORU
# ==========================================

def print_progress(conn):

    sql = """
        SELECT
            COUNT(*) AS total,

            COUNT(*) FILTER (
                WHERE s.status = 'completed'
            ) AS completed,

            COUNT(*) FILTER (
                WHERE s.status = 'failed'
            ) AS failed,

            COUNT(*) FILTER (
                WHERE s.yol_id IS NULL
                   OR s.status = 'pending'
            ) AS pending

        FROM yollar y

        INNER JOIN mahalleler m
            ON y.mahalle_id = m.id

        INNER JOIN ilceler i
            ON m.ilce_id = i.id

        LEFT JOIN bina_scraper_state s
            ON y.id = s.yol_id
           AND y.mahalle_id = s.mahalle_id

        WHERE i.il_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (ANTALYA_ID,))
        result = cur.fetchone()

    total, completed, failed, pending = result

    print("\n" + "=" * 50)
    print("BİNA SCRAPER İLERLEME RAPORU")
    print("=" * 50)

    print(f"Toplam yol-mahalle ilişkisi: {total}")
    print(f"Tamamlanan: {completed}")
    print(f"Hatalı: {failed}")
    print(f"Bekleyen: {pending}")

    if total > 0:
        percentage = completed / total * 100
        print(f"İlerleme: %{percentage:.2f}")

    with conn.cursor() as cur:

        cur.execute("""
            SELECT COUNT(*)
            FROM binalar
        """)

        bina_count = cur.fetchone()[0]

    print(
        f"Veritabanındaki numarataj kaydı: "
        f"{bina_count}"
    )


# ==========================================
# 8. ANA PROGRAM
# ==========================================

def main():

    print("=" * 50)
    print("WISP PLANNER - BİNA / NUMARATAJ SCRAPER")
    print("=" * 50)

    session = requests.Session()

    try:

        with psycopg.connect(
            **DB_CONFIG,
            autocommit=True
        ) as conn:

            yollar = get_pending_yollar(conn)

            print(
                f"İşlenecek benzersiz yol: {len(yollar)}"
            )

            for index, (
                yol_id,
                yol_name,
                ilce_name
            ) in enumerate(yollar, start=1):

                print(
                    f"\n[{index}/{len(yollar)}] "
                    f"{ilce_name} / {yol_name}"
                )

                mahalle_ids = get_pending_mahalle_ids(
                    conn,
                    yol_id
                )

                if not mahalle_ids:
                    continue

                try:

                    features = fetch_binalar(
                        session,
                        yol_id
                    )

                    count = save_binalar(
                        conn,
                        yol_id,
                        mahalle_ids,
                        features
                    )

                    print(
                        f"BAŞARILI: {count} numarataj "
                        f"ilişkisi kaydedildi. "
                        f"API noktası: {len(features)}"
                    )

                except RuntimeError as exc:

                    mark_failed(
                        conn,
                        yol_id,
                        mahalle_ids,
                        exc
                    )

                    print(
                        f"ERİŞİM HATASI: {exc}"
                    )

                    print("Scraper durduruldu.")
                    break

                except requests.RequestException as exc:

                    mark_failed(
                        conn,
                        yol_id,
                        mahalle_ids,
                        exc
                    )

                    print(
                        f"BAĞLANTI HATASI: {exc}"
                    )

                    print("Scraper durduruldu.")
                    break

                except (
                    ValueError,
                    KeyError,
                    psycopg.Error
                ) as exc:

                    # Hata kaydını ayrı transaction'da tut.
                    mark_failed(
                        conn,
                        yol_id,
                        mahalle_ids,
                        exc
                    )

                    print(
                        f"VERİ HATASI: {exc}"
                    )

                    # Diğer yollardan devam et.
                    continue

                # İstekler arasında bekle.
                time.sleep(
                    REQUEST_DELAY +
                    random.uniform(0, 1)
                )

            print_progress(conn)

    except KeyboardInterrupt:

        print(
            "\nProgram kullanıcı tarafından "
            "durduruldu. İlerleme kaydedildi."
        )

    finally:
        session.close()


if __name__ == "__main__":
    main()
