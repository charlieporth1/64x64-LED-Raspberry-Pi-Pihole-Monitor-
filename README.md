# 64x64 LED Raspberry Pi Pi-Hole Monitor
## Project overview
This project using the Adafruit 64x64 LED panel to monitor my PiHole setup remotely and can be run locally
You can purchase a Adafruit 64x64 LED panel [here](https://www.adafruit.com/product/3649)
This project was built and tested with Python3.7 
This project installs [this library](https://github.com/hzeller/rpi-rgb-led-matrix/) in order to print on the display
***

## Project functions 
* Status monitor 
* Systemd process failure alert 

 
## Running && Install
Modify `config-sample.yaml` for your needs 
### Install
```
mv config-sample.yaml config.yaml
source venv/bin/activate
pip install -r requirements.txt
```

# Running
```

source venv/bin/activate 
sudo python3 main.py
```
