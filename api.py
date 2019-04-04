from flask_restful import Api, Resource, reqparse
from flask import Flask
import mysql.connector
import datetime as dt
import requests
import json
import mpu


app = Flask(__name__)
api = Api(app)

MAPS_KEY = "5b3ce3597851110001cf62482e2890bc9f8e432886b7708caecd04e2"
MAPS_URL = "https://api.openrouteservice.org/v2/directions/foot-walking"

WEATHER_KEY = "0a187d268a9951e269589ac49f41a67c"
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
ICON_URL = "http://openweathermap.org/img/w/"

ADMIN_KEY = "12345"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# TODO query from db to select all sites and load them into the python program
# NOTE on export bring dependencies!


""" Response Codes
200 OK, 201 Created, 204 No Content
400 Bad Request (Syntax), 401 Unauthorized (No Key), 403 Forbidden, 404 Not Found
"""

sites = [
    {
        "name": "Akropolis",
        "address": "Max Mustermannstrasse 1",
        "x": 37.9715326,
        "y": 23.7257335,
        "description": "Das ist die Akropolis"
    },
    {
        "name": "Bonzata",
        "address": "Max Sonnleiten 21",
        "x": 37.9215326,
        "y": 23.7557335,
        "description": "Das ist ein anderes Point of Interest!"
    }
]

users = [
    {
        "id": 1,
        "name": "Dominic"
    }
]


class Weather(Resource):

    """Class for handling requests to /weather\n
    Supports ``GET``, ``POST``"""

    def get(self, place=None):
        """Get weather at certain place. If place is not specified 'Athens,GR' will be used by default\n
        :return Returns a dict of the current weather conditions in a specified palce
        """
        if place is None:
            place = "Athens,GR"

        res = requests.get(
            WEATHER_URL, {"q": place, "appid": WEATHER_KEY, "units": "metric"})

        code = res.status_code
        res = res.json()  # Convert to JSON object to read data
        if code == 200:
            return {
                "name": res["name"],
                "date": dt.datetime.now().strftime("%X"),
                "time": dt.datetime.now().strftime("%x"),
                "min_temp": res["main"]["temp_min"],
                "max_temp": res["main"]["temp_max"],
                "temp": res["main"]["temp"],  # Temp in °C
                "humidity": res["main"]["humidity"],  # Percentage
                "icon": res["weather"][0]["icon"],  # Image ID for png
                "description": res["weather"][0]["description"]
            }
        else:
            return "Error: {}".format(res["message"]), res["cod"]


class Sites(Resource):

    """Class for handling requests to /sites\n
    Supports ``GET``"""

    @staticmethod
    def get_distance(lat1, lon1, lat2, lon2):
        """Calculates the distance between two coordinates on a sphere"""
        return mpu.haversine_distance((lat1, lon1), (lat2, lon2))

    def get(self, x=None, y=None, radius=5):
        """Gets all sites or sites in a certain radius from a given coordinate. Defaults to 5 kilometers.\n
        :param x: X coordinate of the user NOTE: Must be a float eg. 2.0
        :param y: Y coordinate of the user NOTE: Must be a float eg. 2.0
        :param radius Radius (kilometers) in which sites should be added to the result array\n
        :return Returns a json object of the list of sites within a given radius of the users position.
        """

        if len(sites) == 0:  # If sites array is empty renew. This should really only happen atthe beginning
            renew_sites()
        # If called sites without arguments
        if x is None and y is None:
            parser = reqparse.RequestParser()
            parser.add_argument("name")
            args = parser.parse_args()

            # If sites called and no name is given then return all sites
            if args["name"] is None:
                return json.dumps(sites), 200

            # Else return all sites with matching name substrings
            new_sites = []
            for site in sites:
                if args["name"].lower() in site["name"].lower():
                    new_sites.append(site)

            if len(new_sites) > 0:
                return json.dumps(new_sites), 200
            else:
                return "Error: Site not found!", 404

        # Otherwise the request was for a radius calculation
        parser = reqparse.RequestParser()
        parser.add_argument("radius")
        args = parser.parse_args()

        # Use specified radius if radius is given
        if args["radius"] is not None:
            radius = float(args["radius"])

        sites_in_radius = []

        for site in sites:
            # Get distance in kilometers and check if site is inside radius
            distance = self.get_distance(site["x"], site["y"], x, y)
            print(
                "Distance between ({}/{}) and ({}/{}): {:.4f}km".format(site["x"], site["y"], x, y, distance))
            if distance < radius:
                site["distance"] = distance
                sites_in_radius.append(site)

        if len(sites_in_radius) > 0:
            return json.dumps(sites_in_radius, indent=4), 200
        else:
            return "No points of interest found within a radius of {}km".format(radius), 404


class Position(Resource):

    """Class for handling requests to /position\n
    Supports ``GET``, ``POST``"""

    def get(self, name):
        """Get position for Person\n
        :return Returns a JSON Object of the user and his last position
        """
        position = get_last_position(name)
        if position is None:
            return "User '{}' does not exist or did not submit a position yet!".format(name), 404
        return json.dumps(position), 200

    def post(self, name):
        """Write position to database under this name"""
        parser = reqparse.RequestParser()
        parser.add_argument("x")
        parser.add_argument("y")
        args = parser.parse_args()

        if args["x"] is None and args["y"] is None:
            return "No coordinates specified!", 400

        user = get_user(name)
        if user is None:
            return "Error: User does not exist!", 404
        # TODO Maybe create user if not exists
        return add_position(user, args["x"], args["y"])


class Route(Resource):

    """Class for handling requests to /route\n
    Supports ``GET``"""

    def get(self, start, end, write_to_file=False):
        """Get Route from point a to point b by foot\n
        :param start Coordinate in format x.xx,y.yy
        :param end Coordinate in format x.xx,y.yy\n
        :return Returns the directions from A to B or Error 400
        """
        res = requests.get(
            MAPS_URL, {"api_key": MAPS_KEY, "start": start, "end": end})

        if res.status_code == 200:
            res = res.json()

            if write_to_file:  # TODO Remove later
                with open("dir.json", "w") as f:
                    json.dump(res, f, indent=4)

            return json.dumps(res, indent=4), 200
        else:
            return "Error: Route could not be calculated!\nError: {}".format(res.text), 400


class AdminSite(Resource):

    def post(self, name):
        parser = reqparse.RequestParser()
        parser.add_argument("key")
        parser.add_argument("address")
        parser.add_argument("x")
        parser.add_argument("y")
        parser.add_argument("description")
        args = parser.parse_args()

        if args["key"] != ADMIN_KEY:
            return "Error: Invalid key!", 401

        if args["address"] is None or args["x"] is None or args["y"] is None or args["description"] is None:
            return "Error: You must specify all variables!", 400

        for site in sites:
            if site["name"].lower() == name.lower():
                # Site exists, change info that is different TODO alter table
                site["address"] = args["address"]
                site["x"]: float(args["x"])
                site["y"]: float(args["y"])
                site["description"]: args["description"]
                return "{} updated successfully!".format(name), 200

        # TODO database create new item
        d = {
            "name": name,
            "address": args["address"],
            "x": float(args["x"]),
            "y": float(args["y"]),
            "description": args["description"]
        }
        # append to array
        return json.dumps(d), 200

    def delete(self, name):
        parser = reqparse.RequestParser()
        parser.add_argument("key")
        args = parser.parse_args()

        if args["key"] != ADMIN_KEY:
            return "Error: Invalid key!", 401

        for site in sites:
            if site["name"].lower() == name.lower():
                # TODO remove from database
                print("Removed ", name)

                return "Removed {}!".format(name), 200

        return "Error: Site not found!", 404


def db_connect():
    """Connects to database\n
    :return Returns an instance of a MySQL Connection
    """
    cnx = mysql.connector.connect(
        user="root", password="mysql#5BT", host="localhost", database="python", auth_plugin="mysql_native_password")

    return cnx


def renew_sites():
    """Updates site array with newest sites by fetching all from mysql database"""
    cnx = db_connect()
    cursor = cnx.cursor()
    cursor.execute("SELECT * FROM sites")

    # Update all known sites
    sites.clear()
    for entry in cursor.fetchall():
        # Name, Address, X, Y, Description
        sites.append({
            "name": entry[1],
            "address": entry[2],
            "x": entry[3],
            "y": entry[4],
            "description": entry[5]
        })
    cnx.close()  # Close due to resource leakage


def get_last_position(name):
    """Gets last known position of a user by name\n
    :return A dictionary of the user and the last known coordinates, together with a timestamp
    """
    cnx = db_connect()
    cursor = cnx.cursor()
    mysql_f = "%Y-%m-%d %H:%M:%S"  # Format of MYSQL dates

    vals = (name,)  # Create tuple to prevent injection
    cursor.execute(
        "SELECT * FROM users JOIN positions ON users.u_id = positions.p_id WHERE kuerzel LIKE %s", vals)

    res = cursor.fetchall()
    cnx.close()  # Close due to resource leakage
    if res is None or len(res) == 0:
        return None

    entry = res[len(res) - 1]  # Get last position TODO check if this works

    if entry[6] is None or entry[7] is None:  # TODO check if i need to do this or if it worx
        return "No poitions", 404

    return {
        "kuerzel": entry[1],
        "vorname": entry[2],
        "nachname": entry[3],
        "x": entry[6],
        "y": entry[7],
        "dt": dt.datetime.strptime(str(entry[8]), mysql_f).strftime(DATE_FORMAT)
    }


def get_user(name):
    """Get user object by name eg. stschdom\n
    :param name The username for a given user\n
    :return Returns a dictionary with the user id, name, firstname and lastname or None if he does not exist
    """
    cnx = db_connect()
    cursor = cnx.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE kuerzel LIKE %s", (name,))

    res = cursor.fetchall()
    cnx.close()  # Close due to resource leakage
    if res is None or len(res) == 0:
        return None

    # Get last entry TODO check if this works and if i need this
    entry = res[len(res) - 1]

    return {
        "id": entry[0],
        "kuerzel": entry[1],
        "vorname": entry[2],
        "nachname": entry[3]
    }


def add_position(user, x, y):
    """Add new position for a given user\n
    :param user: The user Object containing id, name, firstname and lastname
    :param x: The new x coordinate
    :param y: The new y coordinate\n
    :return Returns A string and HTTP status code for answering the API request
    """
    cnx = db_connect()
    cursor = cnx.cursor()

    try:
        vals = (user["id"], x, y, dt.datetime.now().strftime(DATE_FORMAT))
        cursor.execute(
            "INSERT INTO positions (p_uid, p_x, p_y, p_dt) VALUES (%s, %s, %s, %s)", vals)

        cnx.commit()
        cnx.close()  # Close due to resource leakage
        return "Position added successfully!", 201
    except:
        return "Error: Syntax error inserting new position for {}!".format(user), 400


# You must call as a float 2.0 or you will get a 404 error
api.add_resource(
    Sites, "/sites", "/sites/<float:x>/<float:y>", endpoint="sites")
api.add_resource(Weather, "/weather",
                 "/weather/<string:place>", endpoint="weather")
api.add_resource(Position, "/position/<string:name>")
api.add_resource(Route, "/route/<string:start>/<string:end>")
api.add_resource(AdminSite, "/site/<string:name>")
app.run(debug=True) # TODO do not use run in a production environment, check function documentations
