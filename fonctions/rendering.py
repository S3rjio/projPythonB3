import pandas as pd
import plotly.express as px
import streamlit as st
from classes.classWeatherAPI import WeatherAPIClient
from classes.classData import DataProcessor
import io
from fonctions.rapport_pdf import create_report
import datetime
from typing import Any, Dict, List
import requests
from fonctions.search_city import search_cities


DEFAULT_CITIES = {
    "Grenoble": {"lat": 45.1786, "lon": 5.7147},    
    "Paris": {"lat": 48.8566, "lon": 2.3522},
    "Lyon": {"lat": 45.7640, "lon": 4.8357},
    "Marseille": {"lat": 43.2965, "lon": 5.3698},
    "London": {"lat": 51.5074, "lon": -0.1278},
    "Madrid": {"lat": 40.4168, "lon": -3.7038}
}

#Mise en cache de la recherche de ville pour 1 heure (les erreurs réseau ne sont pas mises en cache)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_city_search(query: str) -> List[Dict[str, Any]]:
    return search_cities(query)


def render_dashboard():
    """
    Renders Streamlit Web Application Interface.
    Author: Student C (Lead UI/UX)
    """
    st.set_page_config(page_title="Dashboard Météo & AQI", page_icon="🌤️", layout="wide")

    st.title("🌤️ Dashboard Météo & Surveillance Qualité de l'Air")
    st.markdown("Projet 3ᵉ Année Ingénieur — Analyse de données environnementales en temps réel")

    client = WeatherAPIClient()

    # Sidebar Options
    st.sidebar.header("⚙️ Configuration")

    query = st.sidebar.text_input("🔍 Rechercher une ville", placeholder="Ex : Grenoble, Tokyo...")

    results: List[Dict[str, Any]] = []
    search_error = False
    if query:
        try:
            results = cached_city_search(query)
        except requests.exceptions.RequestException:
            search_error = True

    if results:
        options = {
            f"{r['name']} ({', '.join(filter(None, [r.get('admin2'), r.get('admin1'), r.get('country')]))})": r
            for r in results
        }
        choice = st.sidebar.selectbox("Résultats de la recherche", list(options.keys()))
        place = options[choice]
        selected_city = place["name"]
        city_info = {"lat": place["latitude"], "lon": place["longitude"]}
    else:
        if search_error:
            st.sidebar.warning("Recherche indisponible (hors ligne ?). Liste par défaut affichée.")
        elif query:
            st.sidebar.warning("Aucune ville trouvée.")
        selected_city = st.sidebar.selectbox("Sélectionner une ville", list(DEFAULT_CITIES.keys()))
        city_info = DEFAULT_CITIES[selected_city]

    mock_mode = st.sidebar.checkbox("Mode Déconnecté / Data Mocked", value=False)
    
    # Fetch Data
    with st.spinner(f"Chargement des données pour {selected_city}..."):
        raw_data = client.fetch_weather_and_air_quality(city_info["lat"], city_info["lon"], mock_mode=mock_mode)
        df = DataProcessor.process_raw_api_data(raw_data)

    if df.empty:
        st.error("Impossible de récupérer ou d'afficher les données.")
        return

    # Add calculated metrics
    df["health_score"] = DataProcessor.calculate_custom_health_index(df)
    latest = df.iloc[0]

    # Alert Box Section
    alerts = DataProcessor.detect_alerts(df)
    if alerts:
        for alert in alerts:
            if alert["level"] == "danger":
                st.error(f"🚨 **DANGER** : {alert['message']}")
            else:
                st.warning(f"⚠️ **ATTENTION** : {alert['message']}")
    else:
        st.success("✅ Qualité de l'air et conditions météorologiques stables. Aucune alerte active.")

    ### Bouton de téléchargement du rapport PDF (lit la base, aucune requête API)
    try:
        buffer = io.BytesIO()
        create_report(selected_city, city_info["lat"], city_info["lon"], buffer)
        st.sidebar.download_button(
            label="📄 Télécharger le rapport PDF",
            data=buffer.getvalue(),
            file_name=f"rapport_meteo_{selected_city}_{datetime.datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf",
        )
    except LookupError as e:
        st.sidebar.caption(f"Rapport PDF indisponible : {e}")
    ### FIN

    # KPI Summary Cards
    st.markdown("---")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    col1.metric("Température", f"{latest['temperature_2m']:.1f} °C")
    col2.metric("Humidité", f"{latest['relativehumidity_2m']:.0f} %")
    col3.metric("Indice AQI (US)", f"{int(latest['us_aqi'])}")
    col4.metric("PM 2.5", f"{latest['pm2_5']:.1f} µg/m³")
    col5.metric("Score Confort (0-100)", f"{latest['health_score']:.1f}")

    # Visualizations
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📈 Évolution Météo", "🏭 Qualité de l'Air", "🗺️ Carte Interactive"])

    with tab1:
        st.subheader("Température et Humidité (7 derniers jours / Prévisions)")
        fig_temp = px.line(
            df, x="datetime", y=["temperature_2m", "relativehumidity_2m"],
            labels={"value": "Valeur", "datetime": "Date/Heure", "variable": "Métrique"},
            title="Série temporelle Météo"
        )
        st.plotly_chart(fig_temp, width="stretch")

    with tab2:
        st.subheader("Concentration des Polluants Clés (µg/m³)")
        fig_air = px.bar(
            df.tail(24), x="datetime", y=["pm2_5", "pm10", "nitrogen_dioxide"],
            barmode="group",
            title="Exposition aux polluants sur les 24 dernières heures"
        )
        st.plotly_chart(fig_air, width="stretch")

    with tab3:
        st.subheader("Localisation de la station de suivi")
        aqi = latest["us_aqi"]
        map_df = pd.DataFrame([{
            "lat": city_info["lat"],
            "lon": city_info["lon"],
            "city": selected_city,
            "aqi": 0 if pd.isna(aqi) else int(aqi)
        }])
        fig_map = px.scatter_map(
            map_df, lat="lat", lon="lon",
            hover_name="city", hover_data=["aqi"],
            text="city",                      # affiche le nom sur la carte
            color_discrete_sequence=["fuchsia"],
            height=450,
        )
        fig_map.update_traces(marker=dict(size=18), textposition="top center")
        fig_map.update_layout(
            map_style="open-street-map",
            map_center={"lat": city_info["lat"], "lon": city_info["lon"]},
            map_zoom=10,
            margin=dict(l=0, r=0, t=0, b=0),
        )
        st.plotly_chart(fig_map, width="stretch", key=f"map_{selected_city}")