#include "M5AtomS3.h"
#include "ArduinoHWCDCHardware.h"
#include "ros/node_handle.h"
namespace ros{
  typedef NodeHandle_<ArduinoHardware, 50, 50, 8192, 8192> NodeHandle;
}
#include <std_msgs/Float32.h>

#include "config.h"
#include "common.h"

#include "battery_display/battery_display.h"

ros::NodeHandle nh;

BatteryDisplay batDisp(&nh);

void setup()
{
  // For display
  M5.Lcd.init();
  M5.Lcd.setRotation(lcd_rotation);
  M5.Lcd.clear();
  M5.Lcd.setTextSize(1.5);

  M5.Lcd.println("waiting for rosserial connection");

  nh.initNode();

  M5.begin();
  batDisp.displayFrame();

  while (!nh.connected()) {
    nh.spinOnce();
    delay(100);
  }

  batDisp.init(); // init after rosserial is connected to access ros parameter server

  int bat_cell = batDisp.getBatCell();
  M5.Lcd.printf("bat_cell is %d", bat_cell);
  M5.Lcd.println();
  M5.Lcd.println("rosserial init done!");

  delay(2000);
}

void loop()
{
  nh.spinOnce();

  M5.Lcd.clear();
  M5.Lcd.setCursor(0, 0);
  if(!nh.connected())
    {
      M5.Lcd.fillScreen(M5.Lcd.color565(255, 0, 0));
    }
  else
    {
      batDisp.updateVoltage();
    }
  delay(500);
}
