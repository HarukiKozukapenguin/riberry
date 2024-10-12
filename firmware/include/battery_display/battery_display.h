#ifndef BatteryDisplay_h
#define BatteryDisplay_h

#include "M5AtomS3.h"

#define LCD_H M5.Lcd.height()
#define LCD_W M5.Lcd.width()

// voltage unit: V
class BatteryDisplay
{
public:
  BatteryDisplay(ros::NodeHandle* nh);

public:
  void displayFrame();
  void updateVoltage();
  int getBatCell() {return bat_cell_;}
  void init();

  static constexpr float VOLTAGE_100P =  4.2;
  static constexpr float VOLTAGE_90P =  4.085;
  static constexpr float VOLTAGE_80P =  3.999;
  static constexpr float VOLTAGE_70P =  3.936;
  static constexpr float VOLTAGE_60P =  3.883;
  static constexpr float VOLTAGE_50P =  3.839;
  static constexpr float VOLTAGE_40P =  3.812;
  static constexpr float VOLTAGE_30P =  3.791;
  static constexpr float VOLTAGE_20P =  3.747;
  static constexpr float VOLTAGE_10P =  3.1;
  static constexpr float VOLTAGE_0P =  3.0;

private:
  ros::NodeHandle* nh_;
  ros::Subscriber<std_msgs::Float32, BatteryDisplay> battery_voltage_sub_;

  int bat_cell_;
  float battery_voltage_;

  void batteryVoltageCallback(const std_msgs::Float32& msg);
  float calcPercentage(float voltage);
  void rosParamInit();
};

inline BatteryDisplay::BatteryDisplay(ros::NodeHandle* nh):
  nh_(nh),
  battery_voltage_sub_("battery_voltage_status", &BatteryDisplay::batteryVoltageCallback, this)
{
  nh->subscribe(battery_voltage_sub_);
}

inline void BatteryDisplay::init()
{
  rosParamInit();
}

inline void BatteryDisplay::rosParamInit()
{
  nh_->getParam("bat_info/bat_cell", &bat_cell_);
}

inline void BatteryDisplay::displayFrame()
{
  // Show title.
  M5.Lcd.fillRect(0, 0, LCD_W, 16, MAROON);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.drawString("Voltage", 0, 0, 1);

  // Show units.
  M5.Lcd.drawRect(0, 19, LCD_W, 19, YELLOW);
  M5.Lcd.drawLine(LCD_W/2+12, 19, LCD_W/2+12, 37, YELLOW);
  M5.Lcd.drawString("V", LCD_W/2-1, 22, 1);
  M5.Lcd.drawString("%", LCD_W-12, 22, 1);
}

inline float BatteryDisplay::calcPercentage(float voltage)
{
  float average_voltage = voltage / bat_cell_;
  float input_cell = voltage / VOLTAGE_100P;
  float percentage = 0;
  if(average_voltage  > VOLTAGE_90P) percentage = (average_voltage - VOLTAGE_90P) / (VOLTAGE_100P - VOLTAGE_90P) * 10 + 90;
  else if (average_voltage  > VOLTAGE_80P) percentage = (average_voltage - VOLTAGE_80P) / (VOLTAGE_90P - VOLTAGE_80P) * 10 + 80;
  else if (average_voltage  > VOLTAGE_70P) percentage = (average_voltage - VOLTAGE_70P) / (VOLTAGE_80P - VOLTAGE_70P) * 10 + 70;
  else if (average_voltage  > VOLTAGE_60P) percentage = (average_voltage - VOLTAGE_60P) / (VOLTAGE_70P - VOLTAGE_60P) * 10 + 60;
  else if (average_voltage  > VOLTAGE_50P) percentage = (average_voltage - VOLTAGE_50P) / (VOLTAGE_60P - VOLTAGE_50P) * 10 + 50;
  else if (average_voltage  > VOLTAGE_40P) percentage = (average_voltage - VOLTAGE_40P) / (VOLTAGE_50P - VOLTAGE_40P) * 10 + 40;
  else if (average_voltage  > VOLTAGE_30P) percentage = (average_voltage - VOLTAGE_30P) / (VOLTAGE_40P - VOLTAGE_30P) * 10 + 30;
  else if (average_voltage  > VOLTAGE_20P) percentage = (average_voltage - VOLTAGE_20P) / (VOLTAGE_30P - VOLTAGE_20P) * 10 + 20;
  else if (average_voltage  > VOLTAGE_10P) percentage = (average_voltage - VOLTAGE_10P) / (VOLTAGE_20P - VOLTAGE_10P) * 10 + 10;
  else percentage = (average_voltage - VOLTAGE_0P) / (VOLTAGE_10P - VOLTAGE_0P) * 10;
  return percentage;
}

inline void BatteryDisplay::updateVoltage()
{
  float voltageRatio = calcPercentage(battery_voltage_) / 100;
  voltageRatio = constrain(voltageRatio, 0.0f, 1.0f);

  // Erase screen.
  M5.Lcd.fillRect(1, 20, 60, 16, BLACK);
  M5.Lcd.fillRect(LCD_W/2+17, 20, 32, 16, BLACK);

  // Show voltage.
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.setCursor(2, 21);
  M5.Lcd.printf("%0.2f", battery_voltage_);
  M5.Lcd.drawString("V", LCD_W/2, 22, 1);
  M5.Lcd.setCursor(LCD_W/2+25, 21);
  M5.Lcd.print((uint8_t)(voltageRatio*100));
  M5.Lcd.drawString("%", LCD_W-12, 22, 1);

  // Show Meter
  int32_t rect_x = 0;
  int32_t rect_h = 7;
  int32_t rect_w = LCD_W;
  int32_t radius = 3;
  uint8_t barNum = 10;
  for(byte k = 0; k < barNum; k++)
    {
      int32_t rect_y = LCD_H - rect_h - (rect_h + 2) * k;
      uint16_t color = M5.Lcd.color565(16,16,16);
      if(voltageRatio > float(k+1) / barNum)
        {
          color = M5.Lcd.color565(
                                  (uint8_t)(255 - 255 * (k / float(barNum-1))),
                                  (uint8_t)(255 * (k / float(barNum-1))), 0);
        }
      M5.Lcd.fillRoundRect(rect_x, rect_y, rect_w, rect_h, radius, color);
    }
}

inline void BatteryDisplay::batteryVoltageCallback(const std_msgs::Float32& msg)
{
  battery_voltage_ = msg.data;
}

#endif
