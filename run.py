#
# run.py
#

#-------------------------------------
# Running flask app without self sign SSL
#-------------------------------------

from app import create_app, socketio

def main():
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)

if __name__ == "__main__":
    main()
