import logging
from classTestModules import TestDashboardModules
from rendering import render_dashboard

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

if __name__ == "__main__":
    # Standard Execution runs Streamlit application
    render_dashboard()