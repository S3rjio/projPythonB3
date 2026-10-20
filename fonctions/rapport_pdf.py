import datetime
import json
import sqlite3
from typing import Any, BinaryIO, Dict, Optional, Tuple, Union

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CACHE_DB = "data_cache.db"      # même base que le dashboard
MAX_AGE_MINUTES = 30            # même durée de validité que CACHE_TTL_MINUTES
NB_ROWS = 4                     # nombre de mesures horaires affichées dans le détail

# colonne dans les données -> (libellé, unité)
COLUMNS = {
    "temperature_2m": ("Temp.", "°C"),
    "relativehumidity_2m": ("Humidité", "%"),
    "surface_pressure": ("Pression", "hPa"),
    "windspeed_10m": ("Vent", "km/h"),
    "pm2_5": ("PM2.5", "µg/m³"),
    "pm10": ("PM10", "µg/m³"),
    "nitrogen_dioxide": ("NO2", "µg/m³"),
    "us_aqi": ("AQI US", ""),
}

Output = Union[str, BinaryIO]

#   Formate un nombre, ou renvoie 'N/A' si la valeur est manquante (NaN/None)
def _fmt(value, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.{digits}f}"


#    Lit dans la base SQLite la dernière réponse enregistrée pour ces coordonnées.
#    Retourne (données brutes, date d'enregistrement) ou None si rien n'est trouvé.
def load_cached_data(
    lat: float, lon: float, db_path: str = CACHE_DB
) -> Optional[Tuple[Dict[str, Any], datetime.datetime]]:
    key = f"data_{lat}_{lon}"
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT response, timestamp FROM api_cache WHERE key = ?", (key,)
            ).fetchone()
    except sqlite3.Error:
        return None

    if not row:
        return None
    return json.loads(row[0]), datetime.datetime.fromisoformat(row[1])


#   Fusionne météo et qualité de l'air
def _build_dataframe(raw: Dict[str, Any]) -> pd.DataFrame:
    df_weather = pd.DataFrame(raw.get("weather", {}).get("hourly", {}))
    df_air = pd.DataFrame(raw.get("air_quality", {}).get("hourly", {}))
    if df_weather.empty or df_air.empty:
        return pd.DataFrame()

    df = pd.merge(df_weather, df_air, on="time", how="inner")
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)


#   Convertit l'heure d'enregistrement (heure de l'ordinateur) dans le fuseau des données
def _local_reference_time(raw: Dict[str, Any], fetched_at: datetime.datetime) -> datetime.datetime:
    offset = raw.get("weather", {}).get("utc_offset_seconds", 0)
    utc = fetched_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return utc + datetime.timedelta(seconds=offset)


#   Style du tableau dans le PDF
def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


#   Génère le rapport PDF à partir de la base SQLite
def create_report(
    city: str,
    lat: float,
    lon: float,
    output: Output = "rapport_meteo.pdf",
    db_path: str = CACHE_DB,
    max_age_minutes: Optional[int] = MAX_AGE_MINUTES,
) -> Output:
    """
    `output` : chemin de fichier ("rapport.pdf") ou buffer (io.BytesIO).
    `max_age_minutes` : âge maximal des données en base (None pour ne pas vérifier).
    Lève LookupError si la base ne contient pas de données exploitables.
    """
    cached = load_cached_data(lat, lon, db_path)
    if cached is None:
        raise LookupError(f"aucune donnée en base pour {city}.")
    raw, fetched_at = cached

    age_minutes = (datetime.datetime.now() - fetched_at).total_seconds() / 60
    if max_age_minutes is not None and age_minutes > max_age_minutes:
        raise LookupError(
            f"les données de la base ont {age_minutes:.0f} min (maximum {max_age_minutes} min)."
        )

    df = _build_dataframe(raw)
    if df.empty:
        raise LookupError("les données de la base sont incomplètes.")


#   Mesures horaires jusqu'à l'heure d'enregistrement (on écarte les prévisions futures)
    ref_time = _local_reference_time(raw, fetched_at)
    df = df[df["time"] <= ref_time].tail(NB_ROWS)
    if df.empty:
        raise LookupError("aucune mesure disponible pour la période.")

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Rapport météo - {city}",
    )

    story = [
        Paragraph(f"Rapport météo et qualité de l'air - {city}", styles["Title"]),
        Paragraph(
            f"Données issues de la base locale, enregistrées le "
            f"{fetched_at:%d/%m/%Y à %H:%M} (il y a {age_minutes:.0f} min).",
            styles["Normal"],
        ),
        Spacer(1, 0.4 * cm),
    ]

    # --- Observation courante (pas de 15 min) ---
    current = raw.get("weather", {}).get("current_weather")
    if current:
        story.append(Paragraph("Observation courante", styles["Heading2"]))
        story.append(Paragraph(
            f"Relevé de {str(current.get('time', ''))[-5:] or 'N/A'} : "
            f"température {_fmt(current.get('temperature'))} °C, "
            f"vent {_fmt(current.get('windspeed'))} km/h "
            f"(direction {_fmt(current.get('winddirection'), 0)}°).",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.4 * cm))

    # --- Dernières mesures horaires ---
    story.append(Paragraph("Dernières mesures horaires", styles["Heading2"]))
    header = ["Date / heure"] + [
        f"{label}\n({unit})" if unit else label for label, unit in COLUMNS.values()
    ]
    rows = [header]
    for _, row in df.iterrows():
        rows.append(
            [row["time"].strftime("%d/%m %H:%M")]
            + [_fmt(row.get(col)) for col in COLUMNS]
        )
    table = Table(rows, colWidths=[2.6 * cm] + [1.8 * cm] * len(COLUMNS))
    table.setStyle(_table_style())
    story += [table, Spacer(1, 0.6 * cm)]

    story.append(Paragraph(
        "Tableau des mesures heure par heure. La dernière ligne correspond à l'heure en cours. "
        "Source : Open-Meteo (données conservées dans la base locale). "
        f"Rapport généré le {datetime.datetime.now():%d/%m/%Y à %H:%M}.",
        styles["Italic"],
    ))

    doc.build(story)
    return output


if __name__ == "__main__":
    try:
        path = create_report("Paris", 48.8566, 2.3522, "rapport_meteo.pdf")
        print(f"Rapport créé : {path}")
    except LookupError as e:
        print(f"Impossible de créer le rapport : {e}")