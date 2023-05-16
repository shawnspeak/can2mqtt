import signal
import asyncio
from typing import Any, List

import can
from can.notifier import MessageRecipient, Listener
from can.bus import BusABC

import paho.mqtt.client as mqtt

topic_name = "homeassistant/#"

class FezzikSensor:
    def __init__(self, deviceId: int, heartbeatPosition: int, topic: Any, name: Any):
        self.deviceId = deviceId
        self.heartbeatPosition = heartbeatPosition
        self.name = name
        self.uniqueId = topic
        self.lastState = 0
        self.configTopic = "homeassistant/sensor/" + topic + "/config"
        self.stateTopic = "homeassistant/sensor/" + topic + "/state"

    def getConfig(self):
        return "{\"unique_id\": \"" + self.uniqueId + "\", \"name\":\"" + self.name + "\", \"state_topic\":\"" + self.stateTopic + "\", \"device_class\": \"temperature\", \"unit_of_measurement\": \"°F\", \"value_template\": \"{{ value_json.temperature}}\"}"

    def handleCanMessage(self, id: int, data: bytearray, client):
        # print("Can message")
        # print(0x700 + self.deviceId)
        # print(id)
        if (id == 0x700 + self.deviceId):
            if (data[self.heartbeatPosition] != self.lastState):
                self.lastState = data[self.heartbeatPosition]
                client.publish(self.stateTopic, "{\"temperature\": " + str(self.lastState) + "}")
                print("Sent heartbeat state change")


class FezzikRelay:
    def __init__(self, deviceId: int, relayId: int, heartbeatPosition: int, topic: Any, name: Any):
        self.deviceId = deviceId
        self.relayId = relayId
        self.heartbeatPosition = heartbeatPosition
        self.lastState = -1
        self.name = name
        self.uniqueId = topic
        self.configTopic = "homeassistant/switch/" + topic + "/config"
        self.stateTopic = "homeassistant/switch/" + topic + "/state"
        self.commandTopic = "homeassistant/switch/" + topic + "/set"

    def getConfig(self):
        return "{\"unique_id\": \"" + self.uniqueId + "\", \"name\":\"" + self.name + "\", \"command_topic\":\"" + self.commandTopic + "\", \"state_topic\":\"" + self.stateTopic + "\"}"

    def handleCanMessage(self, id: int, data: bytearray, client):
        # print("Can message")
        # print(0x700 + self.deviceId)
        # print(id)
        if (id == 0x700 + self.deviceId):
            if (data[self.heartbeatPosition] != self.lastState):
                self.lastState = data[self.heartbeatPosition]
                client.publish(self.stateTopic, "ON" if self.lastState == 1 else "OFF")
                print("Sent heartbeat state change")

    def handleMqttMessage(self, msg: Any, bus: can.bus.BusABC):
        if (msg.topic == self.commandTopic):
            print("Set message recieved: " + str(msg.payload))

            # turn command into state
            # possibleState = 1 if str(msg.payload) == "ON" else 0 if str(msg.payload) == "OFF" else -1

            # if (possibleState >= 0) and (possibleState != self.lastState):
                # send toggle
            canMsg = can.Message(
                arbitration_id=0x600 + self.deviceId, 
                data=[0x02, self.relayId, 0, 0, 0, 0, 0, 0],
                is_extended_id=False
            )
            try:
                bus.send(canMsg)
                print(f"Message sent on {bus.channel_info}")
            except can.CanError:
                print("Message NOT sent")


class HaMqqt:
    connected = False

    def __init__(self, relays: List[FezzikRelay], sensors: List[FezzikSensor], bus: can.bus.BusABC):
        self.bus = bus
        self.relays = relays
        self.sensors = sensors
        self.client = mqtt.Client("can2mqtt")
        mqtt_host = dict({ "hostname": "localhost", "port": 1883 })
        self.client.username_pw_set("homeassistant", "qwer1234")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.connect(mqtt_host["hostname"], mqtt_host["port"], 60)

    def loop_it(self):
        self.client.loop_start()
        # self.client.loop_forever()

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print("Unexpected disconnection: {}".format(rc) )

    def on_subscribe(self, client, userdata, mid, granted_qos):
        print("Subscribed: mid=" + str(mid) + " QoS=" + str(granted_qos))

    def on_connect(self, client, userdata, flags, rc):
        print("on_connect: " + mqtt.connack_string(rc))

        # publish configs
        for relay in self.relays:
            self.client.publish(relay.configTopic, relay.getConfig(), retain=True)
        
        for sensor in self.sensors:
            self.client.publish(sensor.configTopic, sensor.getConfig(), retain=True)

        # subscribe to everything
        self.client.subscribe(topic_name, 2)
        self.connected = True

    def publish(self, topic, payload):
        self.client.publish(topic, payload)

    def on_message(self, client, userdata, msg):
        print("onMessageArrived: " + msg.topic + " " + str(msg.payload))
        for relay in self.relays:
            relay.handleMqttMessage(msg, self.bus)


class HeartbeatReader(Listener): 

    def __init__(self, client: HaMqqt, relays: List[FezzikRelay], sensors: List[FezzikSensor], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client = client;
        self.lastState = -1
        self.deviceId = 0x40
        self.relays = relays
        self.sensors = sensors

    def on_message_received(self, msg: can.Message) -> None:
        for relay in self.relays:
            relay.handleCanMessage(msg.arbitration_id, msg.data, self.client)
        for sensor in self.sensors:
            sensor.handleCanMessage(msg.arbitration_id, msg.data, self.client)

class MainApp:
    def __init__(self):
        self.shutdown = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

        self.relays = [
            FezzikRelay(0x40, 0, 6, "fez-heater", "Hydronic Heater/Pump"),
            FezzikRelay(0x40, 1, 7, "fez-eng-preheat", "Engine Preheat"),
            FezzikRelay(0x20, 6, 6, "fez-heat-fan", "Hab Heater Fan"),
            FezzikRelay(0x30, 0, 6, "fez-water-pump", "Water Pump"),
        ]

        self.sensors = [
            # FezzikSensor(0x40, 0, "fez-heater-input", "Input Coolant Temp")
        ]

    def exit_gracefully(self, signum, frame):
        print('Received:', signum)
        self.shutdown = True

    def start(self):
        self.bus = can.ThreadSafeBus(
            interface="socketcan", 
            channel="can0",
            bitrate=500000
        )
        self.mqttClient = HaMqqt(self.relays, self.sensors, self.bus);
        self.heartbeater = HeartbeatReader(self.mqttClient, self.relays, self.sensors)

    async def run(self):
        print("Running app")
        self.reader = can.AsyncBufferedReader()

        listeners: List[MessageRecipient] = [
            self.heartbeater,
            self.reader,
        ]

        # Create Notifier with an explicit loop to use for scheduling of callbacks
        loop = asyncio.get_running_loop()
        notifier = can.Notifier(self.bus, listeners, loop=loop)

        self.mqttClient.loop_it();

        while self.shutdown == False:
            msg = await self.reader.get_message()

    def stop(self):
        print("Stop app")


if __name__ == "__main__":
    app = MainApp()

    app.start()

    asyncio.run(app.run())