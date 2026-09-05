"""Vercel entrypoint. The @vercel/python builder targets this file and
expects a module-level WSGI `app` object; the actual application code
lives in the roombooking package.
"""

from roombooking import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
