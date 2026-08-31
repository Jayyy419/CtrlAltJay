"""AWS Lambda entrypoint.

Adapts the existing Flask WSGI app to Lambda's event/response shape via
apig-wsgi, so app.py stays a plain Flask app that still runs under gunicorn
locally and in tests.

The Function URL is invoked by CloudFront and emits the payload format
version 2.0 event shape, hence binary_support plus the explicit v2 handler.
"""

from apig_wsgi import make_lambda_handler

from app import app

# binary_support=True so images, fonts and gzipped responses survive the
# base64 round-trip through Lambda instead of being corrupted as text.
# Anything not matching the default text content types is encoded.
handler = make_lambda_handler(app, binary_support=True)
