# Raspberry Pi Autostart Guide

To run your YOLO demo automatically when the Raspberry Pi starts, the best method is to use a **systemd service**.

## 1. Create the Service File

Create a file named `yolo-demo.service` on your Raspberry Pi:

```bash
sudo nano /etc/systemd/system/yolo-demo.service
```

Paste the following content into it. **IMPORTANT**: You must update the paths to match where you actually copied the files on your Pi.

```ini
[Unit]
Description=YOLO Demo FastAPI Server
After=network.target

[Service]
# Change 'pi' to your username if different
User=pi
Group=pi

# UPDATE THIS: The directory where you put the project files
WorkingDirectory=/home/pi/yvnalv/projects/Training-Project

# UPDATE THIS: Path to your python environment
# If you are NOT using a virtual environment, you can remove the Environment line 
# and just use /usr/bin/python3
Environment="PATH=/home/pi/yvnalv/projects/testtube/bin:/usr/local/bin:/usr/bin:/bin"

# The command to run
# Make sure 'uvicorn' is in the path or use the full path to it
ExecStart=/home/pi/yvnalv/projects/testtube/bin/uvicorn main:app --host 0.0.0.0 --port 8000

# Auto-restart if it crashes
Restart=always

[Install]
WantedBy=multi-user.target
```

## 2. Enable and Start the Service

Run these commands to register the service and start it:

```bash
# Reload systemd to read the new file
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable yolo-demo.service

# Start the service immediately
sudo systemctl start yolo-demo.service
```

## 3. Check Status

To verify it is running or to see errors:

```bash
sudo systemctl status yolo-demo.service
```

To see the logs:

```bash
journalctl -u yolo-demo.service -f
```
