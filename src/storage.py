"""Storage functions for Postgres and Blob Storage."""

import json
import logging
import os
from contextlib import closing
from datetime import datetime, timezone

import pandas as pd
import psycopg2
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

log = logging.getLogger(__name__)


def insert_readings(df: pd.DataFrame) -> None:
    """Insert a DataFrame of weather readings into Postgres."""
    db_url = os.environ["POSTGRES_URL"]
    schema = os.environ.get("DB_SCHEMA", "public")

    with closing(psycopg2.connect(db_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")  # noqa: S608
            cur.execute(f"SET search_path TO {schema}")  # noqa: S608

            cur.execute("""
                CREATE TABLE IF NOT EXISTS weather_readings (
                    id SERIAL PRIMARY KEY,
                    city TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    temperature REAL NOT NULL,
                    humidity REAL NOT NULL,
                    precipitation REAL NOT NULL,
                    wind_speed REAL NOT NULL,
                    wind_speed_ms REAL NOT NULL,
                    is_raining BOOLEAN NOT NULL,
                    UNIQUE (city, timestamp)
                    )
                """)

            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO weather_readings
                        (city, timestamp, temperature, humidity,
                         precipitation, wind_speed, wind_speed_ms, is_raining)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (city, timestamp) DO NOTHING
                    """,
                    (
                        row["city"],
                        row["timestamp"].to_pydatetime(),
                        float(row["temperature"]),
                        float(row["humidity"]),
                        float(row["precipitation"]),
                        float(row["wind_speed"]),
                        float(row["wind_speed_ms"]),
                        bool(row["is_raining"]),
                    ),
                )

        conn.commit()

    log.info("Inserted %d rows into %s.weather_readings", len(df), schema)


def upload_raw_json(raw_data: list[dict]) -> None:
    """Upload raw API response to Blob Storage as a JSON backup."""
    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    client = BlobServiceClient.from_connection_string(conn_str)
    container = client.get_container_client("raw")
    try:
        container.create_container()
    except ResourceExistsError:
        pass

    blob_name = (
        f"pipeline/{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.json"
    )
    container.upload_blob(
        name=blob_name,
        data=json.dumps(raw_data).encode("utf-8"),
        overwrite=True,
    )
    log.info("Uploaded raw data to blob: %s", blob_name)
