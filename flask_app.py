import os
from rest_api import app

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=int(os.environ.get('PORT', 5000)))