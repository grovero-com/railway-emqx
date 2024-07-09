from typer import Typer, Argument, Option
import bcrypt
import psycopg2
from psycopg2 import sql
from typing import Annotated
import paho.mqtt.client as mqtt
import time
import random
import pydantic
import http.server
import socketserver
from rich import print_json
import json

import typed_settings as ts
from urllib.parse import urlparse


class Settings(pydantic.BaseModel):
    broker: str
    client_id: str = "minigro-44444444"
    username: str = ""
    password: str = ""
    db_name: str = "postgres"
    db_user: str = "postgres"
    db_host: str = "localhost"
    db_port: int = 5432
    db_pass: str = "postgres"

    @property
    def _url(self):
        return urlparse(self.broker)

    @property
    def connect_params(self):
        return dict(host=self._url.hostname, port=self._url.port)

    @property
    def transport(self):
        return "websockets" if self._url.scheme.startswith("ws") else "tcp"

    @property
    def farm_id(self):
        parts = self.client_id.split("-", 2)
        return parts[1] if len(parts) > 1 else self.client_id


settings = ts.load(Settings, appname="mqtt")


class Alert(pydantic.BaseModel):
    sensor: str
    message: str


class SensorValue(pydantic.BaseModel):
    type: str
    value: int | float | list[int]
    unit: str | None = None


# Topics:
# 	{id}/sensors
# 	{id}/alert
# 	{id}/command
class FakeFarm:
    def __init__(self, client: mqtt.Client, farm_id: str):
        self._id = farm_id
        self.mqtt = client

    @staticmethod
    def _random_bool(count: int):
        if count < 2:
            return random.choice([0, 1])
        else:
            return [random.choice([0, 1]) for _ in range(count)]

    def publish_sensors(self):
        data = [
            SensorValue(
                type="ambient_light", value=random.randint(10, 1024), unit="lux"
            ),
            # {"type": "ambient_light", "value": , "unit": "lux"},
            SensorValue(type="water_level", value=self._random_bool(2)),
            SensorValue(
                type="water_temperature",
                value=round(random.uniform(14.0, 25.0), 1),
                unit="C",
            ),
            SensorValue(
                type="conductivity",
                value=round(random.uniform(1.0, 2.0), 1),
                unit="mS/cm",
            ),
            SensorValue(type="ph", value=round(random.uniform(3.5, 7.5), 1)),
            SensorValue(
                type="temperature",
                value=round(random.uniform(15.0, 30.0), 1),
                unit="C",
            ),
            SensorValue(type="humidity", value=random.randint(25, 90), unit="%"),
            SensorValue(
                type="doors",
                value=self._random_bool(3),
            ),
        ]
        ta = pydantic.TypeAdapter(list[SensorValue])
        print("sending sensor data:", data)
        res = self.mqtt.publish(f"{self._id}/sensors", ta.dump_json(data))
        self.check_alerts(data)
        return res

    def push_alert(self, data: Alert | dict):
        if isinstance(data, dict):
            data = Alert(**data)
        print("publish alert:", data)
        return self.mqtt.publish(f"{self._id}/alert", data.json())

    def check_alerts(self, data: list[SensorValue]):
        for item in data:
            if "water_level" in item.type:
                v = item.value
                # sensor 1 and 2 no water
                if all(v):
                    self.push_alert(Alert(sensor="water_level", message="no water"))
                elif v[0] == 1 and v[1] == 0:
                    self.push_alert(Alert(sensor="water_level", message="clean sensor"))
                elif v[0] == 0 and v[1] == 1:
                    self.push_alert(Alert(sensor="water_level", message="low water"))
            elif "water_temperature" in item.type:
                if item.value > 22.0:
                    self.push_alert(
                        Alert(sensor="water_temperature", message="high temperature")
                    )
                elif item.value < 15.0:
                    self.push_alert(
                        Alert(sensor="water_temperature", message="low temperature")
                    )
            elif "temperature" in item.type:
                if item.value > 26.0:
                    self.push_alert(
                        Alert(sensor="temperature", message="high temperature")
                    )
                elif item.value < 16.0:
                    self.push_alert(
                        Alert(sensor="temperature", message="low temperature")
                    )
            elif "humidity" in item.type:
                if item.value > 88.0:
                    self.push_alert(Alert(sensor="humidity", message="high humidity"))
                elif item.value < 30.0:
                    self.push_alert(Alert(sensor="humidity", message="low humidity"))


# MQTT topics
def build_topics(machine_id: str):
    return {
        "sensors": f"{machine_id}/sensors",
        "alert": f"{machine_id}/alert",
        "actuator_commands": f"{machine_id}/actuator",
        "control_commands": f"{machine_id}/control",
        "status_updates": f"{machine_id}/status",
        "rtc": f"{machine_id}/rtc",
    }


app = Typer()


@app.command()
def fake(
    client_id: Annotated[str, Option("--id", "--client-id", "-c")] = settings.client_id,
    broker: Annotated[str, Option("--broker", "-b")] = settings.broker,
    username: Annotated[str, Option("--username", "-u")] = settings.username,
    password: Annotated[str, Option("--password", "-p")] = settings.password,
    # transport: Annotated[str, Option("--id", "--client-id", "-c")] = settings.client_id,
):
    settings.broker = broker
    # Initialize MQTT client
    client = mqtt.Client(client_id=client_id, transport=settings.transport)
    client.on_connect = on_connect
    client.on_message = on_message

    if username != "" and password != "":
        client.username_pw_set(username, password)

    print("connecting to broker", settings.broker, settings.connect_params, "...")
    client.connect(**settings.connect_params, keepalive=60)

    # Start the loop
    print("starting MQTT loop...")
    client.loop_start()

    print("MQTT must be connected")
    # Simulate device behavior
    farm = FakeFarm(client, settings.client_id)
    try:
        while True:
            farm.publish_sensors()
            rn = random.randint(1, 1000)
            if rn > 500 and rn < 590:
                farm.push_alert(Alert(sensor="ligh", message="check led"))
            elif rn > 830:
                farm.push_alert(Alert(sensor="water_level", message="refill water"))
            elif rn > 70 and rn < 222:
                farm.push_alert(Alert(sensor="door", message="door opened"))
            elif rn > 200 and rn < 300:
                farm.push_alert(Alert(sensor="peristaltic_pump", message="refill h2o2"))
            elif rn > 300 and rn < 400:
                farm.push_alert(Alert(sensor="door", message="refill nutrients"))
            # elif rn > 400 and rn < 500:
            #     farm.push_alert(Alert(sensor="door", message="door opened"))
            # publish_sensor_data(client)
            # publish_actuator_commands(client)
            # publish_control_commands(client)
            # publish_status_updates(client)
            # publish_rtc(client)
            time.sleep(15)  # Adjust the frequency of updates as needed
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()
        print("Simulation stopped")


@app.command()
def add_user(
    username: Annotated[str, Argument()],
    password: Annotated[str, Option("--password", "-p", prompt=True, hide_input=True)],
    db_name: Annotated[str, Option(envvar=["PGDATABASE"])] = settings.db_name,
    db_host: Annotated[str, Option(envvar=["PGHOST"])] = settings.db_host,
    db_port: Annotated[int, Option(envvar=["PGPORT"])] = settings.db_port,
    db_user: Annotated[str, Option(envvar=["PGUSER"])] = settings.db_user,
    db_pass: Annotated[str, Option(envvar=["PGPASS"])] = settings.db_pass,
    superuser: Annotated[bool, Option("--superuser", "-s")] = False,
):
    conn = psycopg2.connect(
        host=db_host, dbname=db_name, user=db_user, password=db_pass
    )
    try:
        with conn as c:
            insert_user(c, username, password, is_superuser=superuser)
    finally:
        conn.close()


@app.command()
def server(
    port: Annotated[int, Option()] = 8005,
):
    # Set up the server
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        print(f"Serving on port {port}")
        httpd.serve_forever()

def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8"), salt.decode("utf-8")


def insert_user(conn, username, password, is_superuser=False):
    password_hash, salt = hash_password(password)
    try:
        print(
            """
            INSERT INTO mqtt.users (username, password_hash, salt, is_superuser)
            VALUES (%s, %s, %s, %s)
            """
            % (username, password_hash, salt, is_superuser)
        )

        with conn.cursor() as cursor:
            insert_query = sql.SQL(
                """
                INSERT INTO mqtt.users (username, password_hash, salt, is_superuser)
                VALUES (%s, %s, %s, %s)
                """
            )
            cursor.execute(insert_query, (username, password_hash, salt, is_superuser))
        print("User inserted successfully")
    except Exception as error:
        print(f"Error inserting user: {error}")


# Callback for connection
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # client.subscribe([(topics["control_commands"], 0)])


# Callback for message
def on_message(client, userdata, msg):
    print(f"Message received on topic {msg.topic}: {msg.payload.decode()}")
    # Here you can add logic to handle incoming control commands


# def publish_sensor_data(client):
#     sensor_data = {
#         "sensors": [
#             {"type": "ambient_light", "value": random.randint(10, 1024), "unit": "lux"},
#             {
#                 "type": "water_level",
#                 "value": [random.choice([0, 1]), random.choice([0, 1])],
#             },
#             {
#                 "type": "water_temperature",
#                 "value": round(random.uniform(20.0, 25.0), 1),
#                 "unit": "C",
#             },
#             {
#                 "type": "conductivity",
#                 "value": round(random.uniform(1.0, 2.0), 1),
#                 "unit": "mS/cm",
#             },
#             {"type": "ph", "value": round(random.uniform(5.5, 7.5), 1)},
#             {
#                 "type": "temperature",
#                 "value": round(random.uniform(20.0, 30.0), 1),
#                 "unit": "C",
#             },
#             {"type": "humidity", "value": random.randint(40, 80), "unit": "%"},
#             {
#                 "type": "doors",
#                 "value": [
#                     random.choice([0, 1]),
#                     random.choice([0, 1]),
#                     random.choice([0, 1]),
#                 ],
#             },
#         ]
#     }
#     client.publish(topics["sensors"], json.dumps(sensor_data))


# def publish_actuator_commands(client):
#     actuator_commands = {
#         "commands": [
#             {"type": "led_strip", "brightness": random.randint(0, 255)},
#             {"type": "fan1", "speed": random.randint(0, 255)},
#             {"type": "fan2", "speed": random.randint(0, 255)},
#             {"type": "air_pump", "status": random.choice([1, 0])},
#             {"type": "valve1", "status": random.choice([1, 0])},
#             {
#                 "type": "peristaltic_pump1",
#                 "status": random.choice([1, 0]),
#             },
#             {
#                 "type": "peristaltic_pump2",
#                 "status": random.choice([1, 0]),
#             },
#         ]
#     }
#     client.publish(topics["actuator_commands"], json.dumps(actuator_commands))


# def publish_control_commands(client):
#     control_commands = {
#         "commands": [
#             {"type": "start", "timestamp": datetime.utcnow().isoformat()},
#             {"type": "stop", "timestamp": datetime.utcnow().isoformat()},
#             {"type": "reset", "timestamp": datetime.utcnow().isoformat()},
#         ]
#     }
#     client.publish(topics["control_commands"], json.dumps(control_commands))


# def publish_status_updates(client):
#     status_updates = {
#         "status": [
#             {"type": "online", "timestamp": datetime.utcnow().isoformat()},
#             {"type": "offline", "timestamp": datetime.utcnow().isoformat()},
#             {
#                 "type": "error",
#                 "error_code": random.randint(100, 999),
#                 "description": "Sensor failure",
#                 "timestamp": datetime.utcnow().isoformat(),
#             },
#         ]
#     }
#     client.publish(topics["status_updates"], json.dumps(status_updates))


# def publish_rtc(client):
#     rtc_data = {"timestamp": datetime.utcnow().isoformat()}
#     client.publish(topics["rtc"], json.dumps(rtc_data))

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        # Get the length of the data
        content_length = int(self.headers['Content-Length'])
        # Read the data
        post_data = self.rfile.read(content_length)
        # Decode the JSON data
        try:
            json_data = json.loads(post_data)
            print("Received JSON data:")
            print_json(data=json_data, indent=4)
        except json.JSONDecodeError:
            print("Received data is not valid JSON.")
            print(post_data.decode('utf-8'))

        # Send a 200 OK response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "received"}')

if __name__ == "__main__":
    app()
