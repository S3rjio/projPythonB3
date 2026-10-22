import datetime
import unittest
import pandas as pd
from classes.classData import DataProcessor


class TestDashboardModules(unittest.TestCase):
    """
    Unit testing module for verifying data processing & scoring logic.
    """

    def setUp(self):
        self.mock_df = pd.DataFrame({
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "datetime": pd.to_datetime(["2026-01-01T00:00", "2026-01-01T01:00"]),
            "temperature_2m": [21.0, 40.0],
            "relativehumidity_2m": [50.0, 20.0],
            "pm2_5": [10.0, 30.0],
            "pm10": [20.0, 55.0],
            "nitrogen_dioxide": [15.0, 60.0]
        })

    def test_health_index_calculation(self):
        scores = DataProcessor.calculate_custom_health_index(self.mock_df)
        self.assertEqual(len(scores), 2)
        self.assertGreater(scores.iloc[0], scores.iloc[1])

    def test_alerts_detection(self):
        # La 2e ligne (40 °C, PM2.5 = 30, NO2 = 60) dépasse 3 seuils
        alerts = DataProcessor.detect_alerts(self.mock_df.iloc[1])
        self.assertEqual(len(alerts), 3)

    def test_no_alert_when_values_are_normal(self):
        # La 1re ligne (21 °C, PM2.5 = 10, NO2 = 15) ne dépasse aucun seuil
        alerts = DataProcessor.detect_alerts(self.mock_df.iloc[0])
        self.assertEqual(alerts, [])
    def test_health_index_values(self):
        # Ligne 1 : 100 - (0 + 0 + 10*1.2) = 88.0
        # Ligne 2 : 100 - (19*1.5 + 30*0.3 + 30*1.2) = 26.5
        scores = DataProcessor.calculate_custom_health_index(self.mock_df)
        self.assertAlmostEqual(scores.iloc[0], 88.0)
        self.assertAlmostEqual(scores.iloc[1], 26.5)

    def test_get_current_row_ignores_future(self):
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
        df = pd.DataFrame({
            "datetime": [now - datetime.timedelta(hours=1), now, now + datetime.timedelta(hours=1)],
            "pm2_5": [1.0, 2.0, 3.0],
        })
        row = DataProcessor.get_current_row(df)
        self.assertEqual(row["pm2_5"], 2.0)  # l'heure en cours, pas la prévision

    def test_get_current_row_fallback_when_all_future(self):
        future = datetime.datetime.now() + datetime.timedelta(days=1)
        df = pd.DataFrame({
            "datetime": [future, future + datetime.timedelta(hours=1)],
            "pm2_5": [5.0, 6.0],
        })
        row = DataProcessor.get_current_row(df)
        self.assertEqual(row["pm2_5"], 5.0)  # repli sur la première ligne