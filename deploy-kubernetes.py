#!/usr/bin/env python

import argparse
import os
from ssh_paramiko import RemoteServer
import sys
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
        self.args = None
        self.master_node = None

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

    def show_step(self, step):
        """
        Simple function to print the step we are working on
        """

        sys.stdout.flush()
        print("******************************************************")
        print("* {}".format(step))
        print("******************************************************")
        sys.stdout.flush()
        return None

    def connect_to_host(self, ipaddr, numTries=5):
        """
        Connect to a host
        """
        attempt=1
        connected = False

        ssh = RemoteServer(None,
                           username=self.args.USERNAME,
                           password=self.args.PASSWORD,
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

    def node_execute_command(self, ipaddr, command, numTries=5):
        """
        Execute a command via ssh
        """
        ssh = self.connect_to_host(ipaddr, numTries)

        print("Executing Command: %s" % (command))
        rc, stdout, stderr = ssh.execute_cmd(command, timeout=None)
        ssh.close_connection()

        stdout.strip()
        stderr.strip()

        if rc is True:
            print("%s" % stdout)

        return rc, stdout, stderr

    def node_execute_multiple(self, ipaddr, commands):
        """
        execute a list of commands
        """
        for cmd in commands:
            rc, output, error = self.node_execute_command(ipaddr,  cmd)
            if rc is False:
                print("error running: [%s] %s" % (ipaddr, cmd))

    def setup_all_nodes(self):
        """
        Prepare all the nodes

        Install pre-reqs
        """
        _commands = []
        _commands.append("yum install -y docker")
        _commands.append("systemctl enable docker && systemctl start docker")
        _commands.append("setenforce 0")
        _commands.append("yum install -y kubelet kubeadm kubectl")
        _commands.append("systemctl enable kubelet && systemctl start kubelet")
        _commands.append("swapoff -a")

        for ipaddr in self.args.IP:
            self.put_files(ipaddr)
            self.node_execute_multiple(ipaddr, _commands)

    def setup_master(self, ipaddr):
        """
        Prepare a host to run k8s master

        This includes installing some pre-reqs
        """

        self.show_step('Setting up the Master: '.format(ipaddr))
        _commands = []
        _commands.append('kubeadm init --pod-network-cidr=10.244.0.0/16 | tee /tmp/kubeinit-temp')
        _commands.append('grep "kubeadm join --token" /tmp/kubeinit-temp > /tmp/join-temp')
        for ip in self.args.IP:
            _commands.append('scp /tmp/join-temp {}:/tmp/join-command'.format(ip))
        _commands.append('if [ ! -d ~/.kube ]; then mkdir ~/.kube; fi')
        _commands.append('if [ ! -f ~/.kube/config ]; then cp /etc/kubernetes/admin.conf ~/.kube/config; fi ')
        _commands.append('sysctl net.bridge.bridge-nf-call-iptables=1')
        _commands.append("kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/v0.9.1/Documentation/kube-flannel.yml")

        self.node_execute_multiple(ipaddr, _commands)

    def setup_node(self, ipaddr):
        """
        Prepare a host to run k8s node

        This includes installing some pre-reqs
        """

        self.show_step('"Setting up node: '.format(ipaddr))
        if ipaddr != self.master_node:
            _commands = []
            _commands.append('bash /tmp/join-command')
            self.node_execute_multiple(ipaddr, _commands)

    def install_helm(self, ipaddr):
        """
        Prepare a cluster to run helm/tiller

        """

        self.show_step('Setting up helm and tiller')
        helm_installer='https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get'
        _commands = []
        _commands.append('yum install -y wget')
        _commands.append('wget {} -O helm_installer && bash ./helm_installer'.format(helm_installer))
        _commands.append('kubectl create clusterrolebinding add-on-cluster-admin --clusterrole=cluster-admin --serviceaccount=kube-system:default')
        _commands.append('helm init && helm repo update')

        self.node_execute_multiple(ipaddr, _commands)


    def put_files(self, ipaddr):
        """
        put some files to the node

        """

        self.show_step('Putting files')
        ssh = self.connect_to_host(ipaddr)

        ssh.put_file('{}/kubernetes.repo'.format(os.path.dirname(os.path.realpath(sys.argv[0]))),
                     '/etc/yum.repos.d/kubernetes.repo')
        ssh.close_connection()

    def get_files(self, ipaddr):
        """
        Copy some files to save directory

        """

        self.show_step('Getting files')
        ssh = self.connect_to_host(ipaddr)

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
        self.args = parser.parse_args()

        self.master_node = self.args.IP[0]

        self.setup_all_nodes()
        self.setup_master(self.master_node)
        for ip in self.args.IP:
            self.setup_node(ip)
        self.install_helm(self.master_node)
        self.get_files(self.master_node)


# Start program
if __name__ == "__main__":
    deployer = KubernetesDeployer()
    deployer.process()
