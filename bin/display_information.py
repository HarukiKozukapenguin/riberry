#!/usr/bin/env python3

import os
import socket
import subprocess
import sys
import time
import threading
import io
import fcntl
from collections import Counter

import cv2
from colorama import Fore
from i2c_for_esp32 import WirePacker
from pybsc.image_utils import squared_padding_image
from pybsc import nsplit
from filelock import FileLock
from filelock import Timeout
import smbus2


I2C_SLAVE = 0x0703

if sys.hexversion < 0x03000000:
   def _b(x):
      return x
else:
   def _b(x):
      return x.encode('latin-1')


class i2c:

    def __init__(self, device=0x42, bus=5):
        self.fr = io.open("/dev/i2c-"+str(bus), "rb", buffering=0)
        self.fw = io.open("/dev/i2c-"+str(bus), "wb", buffering=0)
        # set device address
        fcntl.ioctl(self.fr, I2C_SLAVE, device)
        fcntl.ioctl(self.fw, I2C_SLAVE, device)

    def write(self, data):
        if type(data) is list:
            data = bytearray(data)
        elif type(data) is str:
            data = _b(data)
        self.fw.write(data)

    def read(self, count):
        return self.fr.read(count)

    def close(self):
        self.fw.close()
        self.fr.close()


# Ensure that the standard output is line-buffered. This makes sure that
# each line of output is flushed immediately, which is useful for logging.
# This is for systemd.
sys.stdout.reconfigure(line_buffering=True)


pisugar_battery_percentage = None
debug_battery = False
debug_i2c_text = False


def identify_device():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()

        if 'Raspberry Pi' in cpuinfo:
            return 'Raspberry Pi'

        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip()

        # remove null character
        model = model.replace('\x00', '')

        if 'Radxa' in model or 'ROCK Pi' in model or model in 'Khadas VIM4':
            return model

        return 'Unknown Device'
    except FileNotFoundError:
        return 'Unknown Device'


def parse_ip(route_get_output):
    tokens = route_get_output.split()
    if "via" in tokens:
        return tokens[tokens.index("via") + 5]
    else:
        return tokens[tokens.index("src") + 1]


def get_ros_ip():
    try:
        route_get = subprocess.check_output(
            ["ip", "-o", "route", "get", "8.8.8.8"],
            stderr=subprocess.DEVNULL).decode()
        return parse_ip(route_get)
    except subprocess.CalledProcessError:
        return None


def wait_and_get_ros_ip(retry=300):
    for _ in range(retry):
        ros_ip = get_ros_ip()
        if ros_ip:
            return ros_ip
        time.sleep(1)
    return None


def get_mac_address(interface='wlan0'):
    try:
        mac_address = subprocess.check_output(
            ['cat', f'/sys/class/net/{interface}/address']).decode(
                'utf-8').strip()
        mac_address = mac_address.replace(':', '')
        return mac_address
    except Exception as e:
        print(f"Error obtaining MAC address: {e}")
        return None


lock_path = '/tmp/i2c-1.lock'

# Global variable for ROS availability and additional message
ros_available = False
ros_additional_message = None
ros_display_image_flag = False
ros_display_image = None
stop_event = threading.Event()


def try_init_ros():
    global ros_available
    global ros_additional_message
    global ros_display_image_flag
    global ros_display_image
    global pisugar_battery_percentage
    ros_display_image_param = None
    prev_ros_display_image_param = None
    while not stop_event.is_set():
        try:
            import rospy
            from std_msgs.msg import String
            from std_msgs.msg import Float32
            import sensor_msgs.msg
            import cv_bridge

            ros_ip = wait_and_get_ros_ip(300)
            print('Set ROS_IP={}'.format(ros_ip))
            os.environ['ROS_IP'] = ros_ip

            def ros_callback(msg):
                global ros_additional_message
                ros_additional_message = msg.data

            def ros_image_callback(msg):
                global ros_display_image
                bridge = cv_bridge.CvBridge()
                ros_display_image = bridge.imgmsg_to_cv2(
                    msg, desired_encoding='bgr8')

            rospy.init_node('atom_s3_display_information_node', anonymous=True)
            rospy.Subscriber('/atom_s3_additional_info', String, ros_callback,
                             queue_size=1)
            battery_pub = rospy.Publisher('/pisugar_battery', Float32,
                                          queue_size=1)
            ros_available = True
            rate = rospy.Rate(1)
            sub = None
            while not rospy.is_shutdown() and not stop_event.is_set():
                ros_display_image_param = rospy.get_param(
                    '/display_image', None)
                if pisugar_battery_percentage is not None:
                    battery_pub.publish(pisugar_battery_percentage)
                if prev_ros_display_image_param != ros_display_image_param:
                    ros_display_image_flag = False
                    if sub is not None:
                        sub.unregister()
                        sub = None
                    if ros_display_image_param:
                        rospy.loginfo('Start subscribe {} for display'
                                      .format(ros_display_image_param))
                        ros_display_image_flag = True
                        sub = rospy.Subscriber(ros_display_image_param,
                                               sensor_msgs.msg.Image,
                                               queue_size=1,
                                               callback=ros_image_callback)
                prev_ros_display_image_param = ros_display_image_param
                rate.sleep()
            if rospy.is_shutdown():
                break
        except ImportError as e:
            print("ROS is not available ({}). Retrying...".format(e))
            time.sleep(5)  # Wait before retrying
        except rospy.ROSInterruptException as e:
            print("ROS interrupted ({}). Retrying...".format(e))
            time.sleep(5)  # Wait before retrying
        finally:
            ros_available = False
            ros_additional_message = None


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
    except socket.error as e:
        print(e)
    ip_address = s.getsockname()[0]
    s.close()
    if ip_address == '0.0.0.0':
        return None
    return ip_address


def get_ros_master_ip():
    master_str = os.getenv('ROS_MASTER_URI', default="None")
    # https://[IP Address]:11311 -> [IP Address]
    master_str = master_str.split(':')
    if len(master_str) > 1:
        master_ip = master_str[1].replace('/', '')
    else:
        return "none"
    return master_ip


def majority_vote(history):
    if not history:
        return 0
    count = Counter(history)
    return count.most_common(1)[0][0]


class PisugarBatteryReader(threading.Thread):

    def __init__(self, bus_number=1, device_address=0x57, alpha=0.9,
                 value_threshold=1000, percentage_threshold=20,
                 history_size=10):
        super().__init__()
        self.bus_number = bus_number
        self.device_address = device_address
        self.alpha = alpha
        self.percentage_threshold = percentage_threshold
        self.history_size = history_size

        self.filtered_percentage = 0
        self.percentage_history = []
        self.charging_history = []

        self.bus = smbus2.SMBus(self.bus_number)
        self.lock = threading.Lock()
        self.running = True

    def read_sensor_data(self, get_charge=False):
        try:
            if get_charge is True:
                value = self.bus.read_byte_data(
                    self.device_address, 0x02) >> 7
            else:
                value = self.bus.read_byte_data(self.device_address, 0x2A)
            return value
        except Exception as e:
            print('[Pisugar Battery Reader] {}'.format(e))
            return None

    def is_outlier(self, current, history, threshold):
        if not history:
            return False
        ratio = sum(abs(current - h) > threshold for h in history) / len(history)
        return ratio > 0.4

    def update_history(self, value, history):
        history.append(value)
        if len(history) > self.history_size:
            history.pop(0)

    def run(self):
        try:
            while self.running:
                percentage = self.read_sensor_data()
                is_charging = self.read_sensor_data(get_charge=True)
                if percentage is None or is_charging is None:
                    time.sleep(0.2)
                    continue

                with self.lock:
                    if self.is_outlier(percentage, self.percentage_history, self.percentage_threshold):
                        pass
                        # print(f"Percentage outlier detected: {percentage:.2f}, history: {self.percentage_history}")
                    else:
                        self.filtered_percentage = self.alpha * percentage + (1 - self.alpha) * self.filtered_percentage
                    # Always update history
                    self.update_history(percentage, self.percentage_history)

                    self.charging_history.append(is_charging)
                    if len(self.charging_history) > self.history_size:
                        self.charging_history.pop(0)

                if debug_battery:
                    print(f"RAW Percentage: {percentage:.2f}")
                    print(f"Filtered Percentage: {self.filtered_percentage:.2f}")
                time.sleep(0.2)
        finally:
            self.bus.close()

    def get_filtered_percentage(self):
        with self.lock:
            return self.filtered_percentage

    def get_is_charging(self):
        with self.lock:
            return majority_vote(self.charging_history) == 1

    def stop(self):
        self.running = False
        self.join()


class DisplayInformation(object):

    def __init__(self, i2c_addr):
        self.i2c_addr = i2c_addr
        self.device_type = identify_device()
        if self.device_type == 'Raspberry Pi':
            import board
            import busio
            self.i2c = busio.I2C(board.SCL, board.SDA)
            bus_number = 1
        elif self.device_type == 'Radxa Zero':
            import board
            import busio
            self.i2c = busio.I2C(board.SCL1, board.SDA1)
            bus_number = 3
        elif self.device_type == 'Khadas VIM4':
            self.i2c = i2c()
            bus_number = None
        else:
            raise ValueError('Unknown device {}'.format(
                self.device_type))
        self.lock = FileLock(lock_path, timeout=10)
        if bus_number:
            self.pisugar_reader = PisugarBatteryReader(bus_number)
            self.pisugar_reader.daemon = True
            self.pisugar_reader.start()
        else:
            self.pisugar_reader = None

    def display_image(self, img):
        img = squared_padding_image(img, 128)
        quality = 75
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        result, jpg_img = cv2.imencode('.jpg', img, encode_param)
        jpg_size = len(jpg_img)

        header = []
        header += [0xFF, 0xD8, 0xEA]
        header += [(jpg_size & 0xFF00) >> 8,
                   (jpg_size & 0x00FF) >> 0]

        packer = WirePacker(buffer_size=1000)
        for h in header:
            packer.write(h)
        packer.end()

        if packer.available():
            self.i2c_write(packer.buffer[:packer.available()])

        time.sleep(0.005)

        for pack in nsplit(jpg_img, n=50):
            packer.reset()
            for h in [0xFF, 0xD8, 0xEA]:
                packer.write(h)
            for h in pack:
                packer.write(h)
            packer.end()
            if packer.available():
                self.i2c_write(packer.buffer[:packer.available()])
            time.sleep(0.005)

    def display_information(self):
        global ros_available
        global ros_additional_message
        global pisugar_battery_percentage

        ip = get_ip_address()
        if ip is None:
            ip = 'no connection'
        ip_str = '{}:\n{}{}{}'.format(
            socket.gethostname(), Fore.YELLOW, ip, Fore.RESET)
        master_str = 'ROS_MASTER:\n' + Fore.RED + '{}'.format(
            get_ros_master_ip()) + Fore.RESET
        battery_str = ''
        if self.pisugar_reader:
            battery = self.pisugar_reader.get_filtered_percentage()
            pisugar_battery_percentage = battery
            if battery is None:
                battery_str = 'Bat: None'
            else:
                if battery <= 20:
                    battery_str = 'Bat: {}{}%{}'.format(
                        Fore.RED, int(battery), Fore.RESET)
                else:
                    battery_str = 'Bat: {}{}%{}'.format(
                        Fore.GREEN, int(battery), Fore.RESET)
            # charging = battery_charging()
            charging = self.pisugar_reader.get_is_charging()
            if charging is True:
                battery_str += '+'
            elif charging is False:
                battery_str += '-'
            else:
                battery_str += '?'
        sent_str = '{}\n{}\n{}\n'.format(
            ip_str, master_str, battery_str)

        if ros_available and ros_additional_message:
            sent_str += '{}\n'.format(ros_additional_message)
            ros_additional_message = None

        if debug_i2c_text:
            print('send the following message')
            print(sent_str)
        packer = WirePacker(buffer_size=len(sent_str) + 8)
        for s in sent_str:
            packer.write(ord(s))
        packer.end()
        if packer.available():
            self.i2c_write(packer.buffer[:packer.available()])

    def display_qrcode(self, target_url=None):
        header = [0x02]
        if target_url is None:
            ip = get_ip_address()
            if ip is None:
                print('Could not get ip. skip showing qr code.')
                return
            target_url = 'http://{}:8085/riberry_startup/'.format(ip)
        header += [len(target_url)]
        header += list(map(ord, target_url))
        packer = WirePacker(buffer_size=100)
        for h in header:
            packer.write(h)
        packer.end()
        if packer.available():
            self.i2c_write(packer.buffer[:packer.available()])

    def i2c_write(self, packet):
        try:
            self.lock.acquire()
        except Timeout as e:
            print(e)
            return
        try:
            self.i2c.writeto(self.i2c_addr, packet)
        except OSError as e:
            print(e)
        except TimeoutError as e:
            print('I2C Write error {}'.format(e))
        try:
            self.lock.release()
        except Timeout as e:
            print(e)
            return

    def run(self):
        global ros_display_image
        global ros_display_image_flag

        while not stop_event.is_set():
            if ros_display_image_flag and ros_display_image is not None:
                self.display_image(ros_display_image)
            else:
                if get_ip_address() is None:
                    if self.device_type == 'Raspberry Pi':
                        ssid = f'raspi-{get_mac_address()}'
                    elif self.device_type == 'Radxa Zero':
                        ssid = f'radxa-{get_mac_address()}'
                    else:
                        ssid = f'radxa-{get_mac_address()}'
                    self.display_qrcode(f'WIFI:S:{ssid};T:nopass;;')
                    time.sleep(3)
                else:
                    self.display_information()
                    time.sleep(3)
                    self.display_qrcode()
                    time.sleep(3)


if __name__ == '__main__':
    display_thread = threading.Thread(target=DisplayInformation(0x42).run)
    display_thread.daemon = True
    display_thread.start()

    try:
        try_init_ros()
    except KeyboardInterrupt:
        print("Interrupted by user, shutting down...")
        stop_event.set()
        display_thread.join()
