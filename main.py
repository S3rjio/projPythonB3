import logging
from classes.classTestModules import TestDashboardModules
from fonctions.rendering import render_dashboard

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

if __name__ == "__main__":
    # Standard Execution runs Streamlit application
    ##pip install streamlit, reportlab##
    render_dashboard()