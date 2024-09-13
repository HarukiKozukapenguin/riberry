# Atom S3 Rosserial Display

This is firmware that displays information on atom s3 via rosserial.

### Prerequirements

Install udev to give permission to the device.

```
curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules | sudo tee /etc/udev/rules.d/99-platformio-udev.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Ubuntu/Debian users may need to add own “username” to the “dialout” group if they are not “root”, doing this issuing

```
sudo usermod -a -G dialout $USER
sudo usermod -a -G plugdev $USER
```

```
pip3 install platformio -U
```

### Generate rosserial library
```
cd firmware
rosrun rosserial_arduino make_libraries.py
```

### Compile and write firmware to atom s3
**When writing to atoms3, push reset button on atoms3 for 2s to make atoms3 write mode.**
```
pio run -t upload
```

### Connect by rosserial
```
rosrun rosserial_python _port:=/dev/tty**** __ns:=robot_ns
```
