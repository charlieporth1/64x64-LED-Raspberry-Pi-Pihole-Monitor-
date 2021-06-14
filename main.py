#!/usr/bin/env python3
import requests, json
import os
import paramiko
import yaml
import time
import random
import asyncio
import threading

repo = 'rpi-rgb-led-matrix'
repo_dir = '/root/' + repo
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
default_port = 8443
default_scheme = 'https'


def read_config_file():
    with open("config.yaml", 'r') as f:
        config_yaml_values = yaml.load(f, Loader=yaml.FullLoader)
        return config_yaml_values['main']


yaml_file = read_config_file()


def exit_scroll():
    # ps -aux | grep "scrolling-text-example" | grep -v grep | awk '{print $2}' | xargs sudo kill -9
    os.system("ps -aux | grep \"" + print_bin + "\" | grep -v grep | awk '{print $2}' | xargs sudo kill -9 ")


exit_scroll()


def install_led_interface():
    print("LED API not found installing")
    os.system("sudo apt update && sudo apt install -y git")
    os.system("cd ~/ && git clone " + led_api_git_url)
    os.system("cd " + repo_dir + " &&  make -C examples-api-use")
    os.system("cd " + repo_dir + "/examples-api-use && cp -rf ./" + print_bin + " /usr/local/bin")


def print_is_running():
    process_count = int(os.system("ps -aux | grep \"" + print_bin + "\" | grep -v grep | awk '{print $2}' | wc -l"))
    return process_count > 0


async def print_status(args='', x=0, y=0, color=None):
    if color is None:
        color = random_color()
    print_bin_options = "-f {0} -s {1} -l {2} -C {3} -x {4} -y {5}".format(default_font, scroll_speed, 1,
                                                                           color, x, y)
    os.system(print_bin + " " + print_bin_options + " " + led_default_options + " " + args)
    while True:
        await asyncio.sleep(1)
        print("print_is_running()", print_is_running())
        if not print_is_running():
            print("print_is_running()", print_is_running())
            await asyncio.sleep(8)
            exit_scroll()
            break


async def pihole_api(hostname='pi.hole', port=80, http_scheme='http'):
    url = "{0}://{1}:{2}/admin/api.php?summaryRaw".format(http_scheme, hostname, port)
    r = requests.get(url)
    pihole_api_json = json.loads(r.text)
    ads_blocked_today = pihole_api_json['ads_blocked_today']
    ads_percentage_today = str(round(pihole_api_json["ads_percentage_today"])) + "%"
    clients_ever_seen = str(pihole_api_json["clients_ever_seen"])
    dns_queries_today = pihole_api_json['dns_queries_today']

    await print_status("Host: {0}".format(hostname))
    await print_status("Ads Blocked {0}".format(ads_blocked_today), 0, 20)
    await print_status("Ads Blocked Percentage {0}".format(ads_percentage_today), 0, 40)
    await print_status("Number of Clients {0}".format(clients_ever_seen))
    await print_status("Total DNS Queries {0}".format(dns_queries_today), 0, 20)


def systemd_status_remote_alert(hostname='pi.hole', usrname='pi', passwd_or_private_key='raspberry',
                                service='pihole-FTL.service', is_passwd=True):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if is_passwd:
        ssh.connect(hostname, username=usrname, password=passwd_or_private_key)
    else:
        k = paramiko.RSAKey.from_private_key_file(passwd_or_private_key)
        ssh.connect(hostname=hostname, username=usrname, pkey=k)

    cmd_to_execute = 'systemctl is-failed ' + service
    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd_to_execute)
    failed_str = 'inactive'
    if failed_str in ssh_stdout:
        return "Alert: Systemd Service has failed {0} on host {1}".format(service, hostname)
    else:
        return None


def is_led_interface_installed():
    return os.path.isdir(repo_dir)


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

    async def run_api(hostname):
        async def run():
            await pihole_api(hostname, default_port, default_scheme)
            time.sleep(1.0)

        # asyncio.run(run())
        await run()

    def run_alert(current_host, current_hostname):
        if current_hostname == 'home.ctptech.dev':
            current_hostname = 'ubuntu-server.local'
        async def run():

            try:
                current_host_password = current_host['password']
                is_password = True
            except:
                current_host_password = current_host['private_key']
                is_password = False

            current_host_username = current_host['username']
            for service in services:
                alert_result = systemd_status_remote_alert(current_hostname, current_host_username,
                                                           current_host_password, service, is_password)
                if alert_result is not None:
                    exit_scroll()
                    await print_status(alert_result)

        asyncio.run(run())

    while True:
        for host in hosts:
        # current_host = hosts[1]['aws.ctptech.dev']
            current_host = host[list(host)[0]]
            current_hostname = current_host['hostname']
        # t1 = threading.Thread(target=run_api, args=(current_hostname,))
            t2 = threading.Thread(target=run_alert, args=(current_host,current_hostname,))
        # starting thread 1
        # t1.start()
        # starting thread 2
            t2.start()
            await run_api(current_hostname)


# See PyCharm help at https://www.jetbrains.com/help/pycharm/

if not is_led_interface_installed():
    print("is_led_interface_installed", is_led_interface_installed())
    install_led_interface()

asyncio.run(main())
# main()
