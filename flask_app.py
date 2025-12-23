import os
from rest_api import create_app
from helpers.logger import get_logger

# Initialize logger
logger = get_logger()

app = create_app()

if __name__ == "__main__":
    try:
        app.run(host='0.0.0.0', debug=False, port=int(os.environ.get('PORT', 5000)))
    except Exception as e:
        logger.error(f"Failed to start Flask application: {str(e)}")
        raise