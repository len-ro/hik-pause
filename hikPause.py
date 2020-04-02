#!/usr/bin/env python3

import sys, subprocess, os, shutil
import json
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import re

class HikPause:
    def __init__(self):
        self.script_path = os.path.dirname(os.path.realpath(__file__))
        self.config = json.load(open(os.path.join(self.script_path, 'config.json'), 'r'))
        self.detections = {
            'intrusion': 'Smart/FieldDetection/1',
            'line': 'Smart/LineDetection/1',
            'motion': 'System/Video/inputs/channels/1/motionDetection',
            'pir': 'WLAlarm/PIR'
        }

    def on(self, identifier = None):
        self.pause(False, identifier)

    def off(self, identifier = None):
        self.pause(True, identifier)

    def pause(self, pause, identifier):
        print("pause(%s, %s)" % (pause, identifier))
        selected_location = None
        selected_camera = None
        if identifier:
            identifier = identifier.split('/')
            selected_location = identifier[0]
            if len(identifier) == 2:
                selected_camera = identifier[1]

        print(selected_location, selected_camera)

        for location in self.config:
            name = location['name']
            if (not selected_location) or (selected_location and name == selected_location):
                cameras = location['cameras']
                for camera, ip in cameras.items():
                    if not selected_camera or (selected_camera and camera == selected_camera):
                        print('Checking %s/%s' % (location['name'], camera))
                        if self.is_reachable(ip):
                            print('Camera %s is reachable' % camera)
                            self.pause_camera(pause, location, camera, ip)
                        else:
                            print('Camera %s is not reacheable' % camera)

    def pause_camera(self, pause, location, name, ip):
        config_path = os.path.join(self.script_path, 'cameras', location['name'], ip)

        if pause:
            if not os.path.exists(config_path):
                os.makedirs(config_path)
            self.disable_detections(config_path, ip, location['user'], location['pass'])
        else: #un-pause
            if not os.path.exists(config_path):
                print('Cannot un-pause a camera which has not been paused first, does not have initial config')
                return
            else:
                #write back saved config
                self.restore_detections(config_path, ip, location['user'], location['pass'])

    def restore_detections(self, config_path, ip, user, passwd):
        for detection_name, detection_path in self.detections.items():
            initial_state_file = os.path.join(config_path, '%s-on.xml' % detection_name)
            if os.path.exists(initial_state_file):
                url = 'http://%s/ISAPI/%s' % (ip, detection_path)
                with open(initial_state_file, 'r') as initial_config_file:
                    cfg = initial_config_file.read()
                    self.write_camera_config(url, user, passwd, cfg, 'restore %s' % detection_name)

    def disable_detections(self, config_path, ip, user, passwd):
        """ 
        For all known detection types:
        - get camera config for given detection, 
        - saves the current config in cameras/location[name]/camera[ip]/detection_name.xml 
        - if detection enabled, disables it and stores cameras/location[name]/camera[ip]/detection_name-off.xml
        - change config on camera
        """
        for detection_name, detection_path in self.detections.items():
            url = 'http://%s/ISAPI/%s' % (ip, detection_path)
            r = requests.get(url, auth=HTTPDigestAuth(user, passwd))
            if r.status_code == 200:
                #print(r.content)
                curent_state_file = os.path.join(config_path, '%s.xml' % detection_name)
                print("Writing %s config to %s" % (detection_name, curent_state_file))
                with open(curent_state_file, 'wb') as new_cfg:
                    new_cfg.write(r.content)
                cfg = self.flip_config(config_path, detection_name)
                if cfg:
                    self.write_camera_config(url, user, passwd, cfg, 'disable %s' % detection_name)
            else:
                print("Error %s for %s. Not supported?" % (r.status_code, url))

    def flip_config(self, config_path, detection_name):
        """
        Fetches xml config related to given detection, 
            - if the detection is enabled, disables it while saving current params and returns it
            - otherwise returns null
        """
        config_file = os.path.join(config_path, '%s.xml' % detection_name)
        tree = ET.parse(config_file)
        root = tree.getroot()
        nsre = re.compile('{([^}]+)}')
        ns = re.search(nsre, root.tag)
        if ns:
            ns = ns.group(1)
        
        #print('Default namespace: ', ns)
        found = False
        for child in root:
            localname = re.sub('{[^}]+}', '', child.tag) #remove namespaces
            if localname == 'enabled':
                found = True
                if child.text == 'true':
                    print('Detection enabled in %s' % config_path)
                    child.text = 'false'
                    off_config_file = os.path.join(config_path, '%s-off.xml' % detection_name)
                    on_config_file = os.path.join(config_path, '%s-on.xml' % detection_name)
                    shutil.copy2(config_file, on_config_file)
                    
                    if ns:
                        ET.register_namespace('', ns)

                    tree.write(off_config_file, encoding='utf8')
                    print('New config: %s' % off_config_file)
                    with open(off_config_file, 'r') as new_config:
                        return new_config.read()
                break
        if not found:
            print("Not found")
        return None

    def write_camera_config(self, url, user, passwd, cfg, msg):
        """
        Writes config to camera
        """
        r = requests.put(url, auth=HTTPDigestAuth(user, passwd), data=cfg)
        if r.status_code == 200:
            #TODO more checks
            print("Write config: %s. Response: %s" % (msg, r.content))
        else:
            print("An error %s occured while writing config %s." % (r.status_code, msg))

    def is_reachable(self, ip):
        res = subprocess.call(['ping', '-c', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return (res == 0)


if __name__ == "__main__":
    """
        This script is designed to turn off (pause) detection alarms on hikvision cameras. Works on:
            - motion detection
            - intrusion detection
            - line-crossing detection
            - PIR detection
        Usage:
            - hikPause.py => pauses all reachable cameras and stores their previous config
            - hikPause.py on => un-pauses all reachable cameras using previously stored config
            - hikPause.py location[/camera] [on] => (un-)pauses cameras specified by location and optional camera name.
        A camera is considered reachable if it can be pinged using system tools.
    """
    hikPause = HikPause()
    if len(sys.argv) == 2:
        if sys.argv[1] == 'on':
            hikPause.on()
        else:
            identifier = sys.argv[1]
            hikPause.off(identifier)
    elif len(sys.argv) == 3:
        identifier = sys.argv[1]
        if sys.argv[2] == 'on':
            hikPause.on(identifier)
        else:
            hikPause.off(identifier)
    else:
        hikPause.off()