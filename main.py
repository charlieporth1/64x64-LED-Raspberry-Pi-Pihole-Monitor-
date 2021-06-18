#!/usr/bin/env python3
import requests, json
import os
import paramiko
import yaml
import time
import random
import asyncio
import threading
from subprocess import PIPE, run
import re
repo = 'rpi-rgb-led-matrix'
install_dir = '/opt/'
repo_dir = install_dir + repo
led_api_git_url = 'https://github.com/hzeller/' + repo
print_bin = 'scrolling-text-example'


def random_color():
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    return "{0},{1},{2}".format(r, g, b)


default_font = repo_dir + "/fonts/10x20.bdf"
led_default_options = '--led-cols=64 --led-rows=64 --led-gpio-mapping=adafruit-hat-pwm  --led-pwm-lsb-nanoseconds=100 --led-daemon --led-brightness=100 --led-slowdown-gpio=4'
scroll_speed = 3

default_port = 80
default_scheme = 'http'
default_ssh_port = 22
default_hostname = 'pi.hole'
default_user = 'pi'


def read_config_file():
    with open("config.yaml", 'r') as f:
        config_yaml_values = yaml.load(f, Loader=yaml.FullLoader)
        return config_yaml_values['main']


yaml_file = read_config_file()


def get_shell_path(path='~/'):
    stdout, _ = bash_run("ls {0}".format(path))
    return stdout


def exit_scroll():
    # ps -aux | grep "scrolling-text-example" | grep -v grep | awk '{print $2}' | xargs sudo kill -9
    os.system("ps -aux | grep \"" + print_bin + "\" | grep -v grep | awk '{print $2}' | xargs sudo kill -9 ")


exit_scroll()


def install_led_interface():
    print("LED API not found installing")
    os.system("sudo apt update && sudo apt install -y git")
    os.system("cd {0} && sudo git clone {1}".format(install_dir, led_api_git_url))
    os.system("cd {0} && sudo chown -R $USER:$USER .".format(repo_dir))
    os.system("cd {0} && make -C examples-api-use".format(repo_dir))
    os.system("cd {0}/examples-api-use && sudo cp -rf {1} /usr/local/bin".format(repo_dir, print_bin))


def bash_run(command):
    result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    stdout = result.stdout.replace('\n', '')
    stderr = result.stderr.replace('\n', '')
    return stdout, stderr


def print_is_running():
    stdout, _ = bash_run("ps -aux | grep \"" + print_bin + "\" | grep -v grep | awk '{print $2}' | wc -l")
    process_count = int(stdout)
    return process_count > 0


async def queue_print_run(sleep_time=1, timeout=16):
    timeout_counter = 0
    while print_is_running():
        await asyncio.sleep(sleep_time)
        timeout_counter += 1
        if timeout_counter >= timeout:
            print("Error process timed out")
            break


async def print_status(args='', x=0, y=0, color=None):
    if color is None:
        color = random_color()
    await queue_print_run()
    print_bin_options = "-f {0} -s {1} -l {2} -C {3} -x {4} -y {5}".format(default_font, scroll_speed, 1,
                                                                           color, x, y)
    os.system("sudo " + print_bin + " " + print_bin_options + " " + led_default_options + " " + args)
    await queue_print_run()


async def pihole_api(hostname=default_hostname, port=default_port, http_scheme=default_scheme):
    url = "{0}://{1}:{2}/admin/api.php?summaryRaw".format(http_scheme, hostname, port)
    r = requests.get(url)
    pihole_api_json = json.loads(r.text)
    if pihole_api_json is not None or pihole_api_json is not '':
        ads_blocked_today = pihole_api_json['ads_blocked_today']
        ads_percentage_today = str(round(pihole_api_json["ads_percentage_today"])) + "%"
        clients_ever_seen = str(pihole_api_json["clients_ever_seen"])
        dns_queries_today = pihole_api_json['dns_queries_today']

        await print_status("Host: {0}".format(hostname))
        await print_status("Ads Blocked {0}".format(ads_blocked_today), 0, 20)
        await print_status("Ads Blocked Percentage {0}".format(ads_percentage_today), 0, 40)
        await print_status("Number of Clients {0}".format(clients_ever_seen))
        await print_status("Total DNS Queries {0}".format(dns_queries_today), 0, 20)


def systemd_status_remote_alert(hostname=default_hostname, usrname=default_user, passwd_or_private_key='raspberry',
                                service='pihole-FTL.service', is_passwd=True):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if is_passwd:
        ssh.connect(hostname=hostname, username=usrname, password=passwd_or_private_key)
    else:
        k = paramiko.RSAKey.from_private_key_file(get_shell_path(passwd_or_private_key))
        ssh.connect(hostname=hostname, username=usrname, pkey=k)

    cmd_to_execute = 'systemctl is-failed ' + service
    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd_to_execute)
    std_out_str = ssh_stdout.read().decode()
    print("ssh_stdout", std_out_str)
    failed_regex_tr = '(inactive|(de|)activating|failed)'
    # activating
   # if failed_str in :
    if re.match(failed_regex_tr,std_out_str):
        return "Alert: Systemd Service has failed {0} on host {1}".format(service, hostname)
    else:
        return None


def is_led_interface_installed():
    return os.path.isdir(repo_dir + '/')


async def main():
    master_services = [
        'wg-quick@wg0.service',
        'ads-catcher'
    ]
    services = [
        "unbound.service",
        "pihole-FTL.service",
        "ctp-dns.service",
        "nginx.service",
        "doh-server.service",
        'php7.4-fpm',
        'lighttpd',
    ]
    hosts = yaml_file['hosts']

    async def run_api(host_data, hostname):
        if "http_port" in host_data:
            http_port = host_data['http_port']
        else:
            http_port = default_port

        if "http_scheme" in host_data:
            http_scheme = host_data['http_scheme']
        else:
            http_scheme = default_scheme

        await pihole_api(hostname, http_port, http_scheme)
        time.sleep(1.0)

    async def run_alert(host_data, hostname):
        # async def run():
            host_data_username = current_host['username']
            try:
                host_data_hostname = host_data['override_hostname']
            except:
                host_data_hostname = hostname

            try:
                host_data_password_or_private_key = host_data['password']
                is_password = True
            except:
                host_data_password_or_private_key = host_data['private_key']
                is_password = False

            for service in services:
                alert_result = systemd_status_remote_alert(hostname=host_data_hostname, usrname=host_data_username,
                                                           passwd_or_private_key=host_data_password_or_private_key,
                                                           service=service, is_passwd=is_password)
                print("alert_result, service, host_data_hostname ", alert_result, service, host_data_hostname)
                if alert_result is not None:
                    exit_scroll()
                    await asyncio.sleep(4)
                    exit_scroll()
                    await asyncio.sleep(1)
                    exit_scroll()
                    alert_warning_str = "!---! ALERT ALERT ALERT !---!"
                    alert_color = '255,0,0'
                    await print_status(alert_warning_str,0,0, color=alert_color)
                    await print_status(alert_warning_str,0,20, color=alert_color)
                    await print_status(alert_warning_str,0, 40, color=alert_color)
                    await print_status(alert_result,0,0, color=alert_color)

        # asyncio.run(run())

    while True:
        for host in hosts:
            current_host = host[list(host)[0]]
            current_hostname = current_host['hostname']
        #    try:
        #        t2 = threading.Thread(target=run_alert, args=(current_host, current_hostname,))
        #        t2.start()
        #    except:
        #        print("Thread error")
            try:
                await run_alert(current_host, current_hostname)
                await run_api(current_host, current_hostname)
                # await asyncio.gather(run_api(current_host, current_hostname),run_alert(current_host, current_hostname) )
                # t1 = threading.Thread(target=run_api, args=(current_host, current_hostname,))
                # t1.start()
            except:
                print("")


if not is_led_interface_installed():
    install_led_interface()

asyncio.run(main())
