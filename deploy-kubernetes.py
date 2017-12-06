#!/usr/bin/env python

import argparse
import os
from ssh_paramiko import RemoteServer
import time

class UnableToConnectException(Exception):
    message = "Unable to connect to Server"

    def __init__(self, server):
        self.details = {
            "server": server,
        }
        super(UnableToConnectException, self).__init__(self.message, self.details)


class KubernetesDeployer:
    def __init__(self):
        self.client = None
        self.save_dir = "/tmp"

    def _get_first_token(self, text):
        if len(text.split()) > 0:
            return(text.split()[0])
        return None

    def setup_arguments(self):
        parser = argparse.ArgumentParser(description='Deploy and Configure Kubernetes')

        # node settings
        parser.add_argument('--ip', dest='IP', action='store', nargs='*',
                        help='Space seperated list of IP addresses of the nodes')
        parser.add_argument('--username', dest='USERNAME', action='store',
                        default='root', help='Node Username, default is \"root\"')
        parser.add_argument('--password', dest='PASSWORD', action='store',
                        default='password', help='Node password, default is \"password\"')

        # return the parser object
        return parser

    def connect_to_host(self, ipaddr, username, password, numTries=5):
        """
        Connect to a host
        """
        attempt=1
        connected = False

        ssh = RemoteServer(None,
                           username=username,
                           password=password,
                           log_folder_path='/tmp',
                           server_has_dns=False)
        while (attempt<=numTries and connected==False):
            print("Connecting to: %s" % (ipaddr))

            connected, err = ssh.connect_server(ipaddr, False)
            if connected == False:
                time.sleep(5)
                attempt = attempt + 1

        if connected == False:
            raise UnableToConnectException(ipaddr)

        return ssh

    def node_execute_command(self, ipaddr, username, password, command, numTries=5):
        """
        Execute a command via ssh
        """
        ssh = self.connect_to_host(ipaddr, username, password, numTries)

        print("Executing Command: %s" % (command))
        rc, stdout, stderr = ssh.execute_cmd(command, timeout=None)
        ssh.close_connection()

        stdout.strip()
        stderr.strip()

        if rc is True:
            print("%s" % stdout)

        return rc, stdout, stderr

    def node_execute_multiple(self, ipaddr, username, password, commands):
        """
        execute a list of commands
        """
        for cmd in commands:
            rc, output, error = self.node_execute_command(ipaddr, username, password, cmd)
            if rc is False:
                print("error running: [%s] %s" % (ipaddr, cmd))

    def setup_all_nodes(self, args):
        """
        Prepare all the nodes

        Install pre-reqs
        """
        _commands = []
        _commands.append("yum install -y docker")
        _commands.append("systemctl enable docker && systemctl start docker")

        _commands.append("echo '[kubernetes]' > /etc/yum.repos.d/kubernetes.repo")
        _commands.append("echo 'baseurl=https://packages.cloud.google.com/yum/repos/kubernetes-el7-x86_64' >> /etc/yum.repos.d/kubernetes.repo")
        _commands.append("echo 'enabled=1' >> /etc/yum.repos.d/kubernetes.repo")
        _commands.append("echo 'gpgcheck=1' >> /etc/yum.repos.d/kubernetes.repo")
        _commands.append("echo 'repo_gpgcheck=1' >> /etc/yum.repos.d/kubernetes.repo")
        _commands.append("echo 'gpgkey=https://packages.cloud.google.com/yum/doc/yum-key.gpg https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg' >> /etc/yum.repos.d/kubernetes.repo")

        _commands.append("setenforce 0")
        _commands.append("yum install -y kubelet kubeadm kubectl")
        _commands.append("systemctl enable kubelet && systemctl start kubelet")
        _commands.append("swapoff -a")

        for ipaddr in args.IP:
            self.node_execute_multiple(ipaddr, args.USERNAME, args.PASSWORD, _commands)

    def setup_master(self, ipaddr, args):
        """
        Prepare a host to run k8s master

        This includes installing some pre-reqs
        """

        _commands = []
        _commands.append('kubeadm init --pod-network-cidr=10.244.0.0/16 | tee /tmp/kubeinit-temp')
        _commands.append('grep "kubeadm join --token" /tmp/kubeinit-temp > /tmp/join-temp')
        for ip in args.IP:
            _commands.append('scp /tmp/join-temp {}:/tmp/join-command'.format(ip))
        _commands.append('sysctl net.bridge.bridge-nf-call-iptables=1')
        _commands.append("KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/v0.9.1/Documentation/kube-flannel.yml")

        self.node_execute_multiple(ipaddr, args.USERNAME, args.PASSWORD, _commands)

    def setup_node(self, ipaddr, args):
        """
        Prepare a host to run k8s node

        This includes installing some pre-reqs
        """

        if ipaddr != args.IP[0]:
            _commands = []
            _commands.append('bash /tmp/join-command')
            self.node_execute_multiple(ipaddr, args.USERNAME, args.PASSWORD, _commands)

    def save_files(self, ipaddr, args):
        """
        Copy some files to save directory

        """
        ssh = self.connect_to_host(ipaddr, args.USERNAME, args.PASSWORD)

        files = ['/etc/kubernetes/admin.conf', '/tmp/join-command']
        for filename in files:
            basename=os.path.basename(filename)
            target='{}/{}'.format(self.save_dir, basename)
            ssh.get_file(target, filename)

        ssh.close_connection()

    def process(self):
        """
        Main logic
        """
        parser = self.setup_arguments()
        args = parser.parse_args()

        self.setup_all_nodes(args)
        self.setup_master(args.IP[0], args)
        for ip in args.IP:
            self.setup_node(ip, args)
        self.save_files(args.IP[0], args)


# Start program
if __name__ == "__main__":
    deployer = KubernetesDeployer()
    deployer.process()
