#!/usr/bin/python
#
# (c) 2015, Joseph Callen <jcallen () csc.com>
# Portions Copyright (c) 2015 VMware, Inc. All rights reserved.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


DOCUMENTATION = '''
module: vcener_vsan_stretch_cluster
Short_description: Creates fault domains and adds a esx host as a witness host, creates diskgroups on
    witness host
description:
    Creates fault domains and adds a esx host as a witness host, creates diskgroups on
    witness host. Module will fail if the cluster has less than 2 esx hosts. You need at least 2
    esx hosts in the cluster for the primary and secondary fault domains.
requirements:
    - pyvmomi 6
    - vsan SDK
    - ansible 2.x
    - esx witness host, physical or witness host appliance in a non vsan cluster
Tested on:
    - vcenter 6
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter with Admin rights
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter user
        required: True
        aliases: ['pass', 'pwd']
    datacenter_name:
        description:
            - The name of the datacenter.
        required: True
    cluster_name:
        description:
            - The name of the vCenter cluster
        required: True
    witness_host:
        description:
            - The host to be used as the witness host
        required: True
    state:
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: VSAN Config Stretch Cluster
  vcenter_vsan_stretch_cluster:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    datacenter_name: "{{ datacenter.name }}"
    cluster_name: "{{ item.name }}"
    witness_host:
      name: "{{ wa_esx_hostname }}"
      num_disk_groups: "{{ item.vsan.num_disk_groups }}"
      num_disks_per_group: "{{ item.vsan.num_disks_per_group }}"
    state: 'present'
  when: item.name == ib_vcenter_nsxedge_esx_cluster_name
  with_items:
    - "{{ datacenter.clusters }}"
  tags:
    - vsan_stretch_cluster
'''


try:
    from pyVim import vim, vmodl, connect
    import requests
    import ssl
    import atexit
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

class VsanStretchCluster(object):
    '''

    '''
    def __init__(self, module):
        self.module = module
        self.cluster_name = module.params['cluster_name']
        self.datacenter_name = module.params['datacenter_name']
        self.witness_host_name = module.params['witness_host']['name']
        self.witness_host_ssd = module.params['witness_host']['num_disk_groups']
        self.witness_host_hdd = module.params['witness_host']['num_disks_per_group']
        self.content = None
        self.si = None
        self.vMos = None
        self.vsan_sc_system = None
        self.cluster = None
        self.witness_host = None
        self.datacenter = None
        self.prefered_fault_domain_name = self.cluster_name + "_FD_01"
        self.second_fault_domain_name = self.cluster_name + "_FD_02"


    def connect_to_vc_api(self, disconnect_atexit=True):

        hostname = self.module.params['hostname']
        username = self.module.params['username']
        password = self.module.params['password']
        validate_certs = self.module.params['validate_certs']

        if validate_certs and not hasattr(ssl, 'SSLContext'):
            self.module.fail_json(
                msg='pyVim does not support changing verification mode with python < 2.7.9. Either update python or or use validate_certs=false')

        try:
            service_instance = connect.SmartConnect(host=hostname, user=username, pwd=password)
        except vim.fault.InvalidLogin, invalid_login:
            self.module.fail_json(msg=invalid_login.msg, apierror=str(invalid_login))
        except requests.ConnectionError, connection_error:
            if '[SSL: CERTIFICATE_VERIFY_FAILED]' in str(connection_error) and not validate_certs:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.verify_mode = ssl.CERT_NONE
                service_instance = connect.SmartConnect(host=hostname, user=username, pwd=password, sslContext=context)
            else:
                self.module.fail_json(msg="Unable to connect to vCenter or ESXi API on TCP/443.",
                                 apierror=str(connection_error))

        if disconnect_atexit:
            atexit.register(connect.Disconnect, service_instance)
        return service_instance


    def vsan_process_state(self):
        '''
        Given desired state and current state process accordingly
        :return: changed, result
        '''

        vsan_states = {
            'absent': {
                'absent': self.state_exit_unchanged,
                'present': self.state_destroy_stretchclsuter,
            },
            'present': {
                'absent': self.state_create_strectcluster,
                'present': self.state_exit_unchanged,
            }
        }

        desired_state = self.module.params['state']
        current_state = self.current_state_stretchcluster()

        vsan_states[desired_state][current_state]()


    def state_exit_unchanged(self):
        '''

        '''
        self.module.exit_json(changed=False, msg='EXIT UNCHANGED')


    def state_destroy_stretchclsuter(self):
        self.module.exit_json(changed=False, msg="DESTROY")


    def state_create_strectcluster(self):

        fault_domain_config = self.vsan_stretch_cluster_fd_config()
        disk_mapping = self.vsan_host_disk_mapping_spec(self.witness_host)

        result = self.vsan_convert_to_stretch(fault_domain_config, disk_mapping)

        if not result:
            self.module.fail_json(msg="failed to create")

        self.module.exit_json(changed=True, result=str(result))


    def current_state_stretchcluster(self):

        state = 'absent'

        try:
            self.si = self.connect_to_vc_api(disconnect_atexit=False)
            self.content = self.si.RetrieveContent()
            self.vMos = GetVsanVcMos(self.si._stub, None)
            self.vsan_sc_system = self.vMos['vsan-stretched-cluster-system']

            self.datacenter = find_datacenter_by_name(self.content, self.datacenter_name)

            if not self.datacenter:
                self.module.fail_json(msg="Cannot find DC")

            self.cluster = find_cluster_by_name_datacenter(self.datacenter, self.cluster_name)

            if not self.cluster:
                self.module.fail_json(msg="Cannot find cluster")

            witness_host = find_hostsystem_by_name(self.content, self.witness_host_name)

            if not witness_host:
                self.module.fail_json(msg="Cannot find witness host")
            else:
                self.witness_host = witness_host

            num_hosts = len(self.cluster.host)

            if num_hosts < 2:
                self.module.fail_json(msg="You do not have the qualified number of hosts for stretch cluster")

            witness_host_present = self.vsan_check_if_witness_host(self.vsan_sc_system, witness_host)

            if witness_host_present:
                state = 'present'

        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg=runtime_fault.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

        return state


    def vsan_check_if_witness_host(self, vsan_sc_system, host):
        is_witness = False

        try:
            is_witness = vsan_sc_system.VSANVcIsWitnessHost(host)
        except vim.fault.VsanFault:
            return is_witness

        return is_witness


    def vsan_stretch_cluster_fd_config(self):

        first_fd_host = []
        second_fd_host = []

        num_hosts = len(self.cluster.host)
        hosts = [host for host in self.cluster.host]

        if (not num_hosts%2):
            for index, item in enumerate(hosts):
                if index < num_hosts/2:
                    first_fd_host.append(item)
            for host in set(hosts) - set(first_fd_host):
                second_fd_host.append(host)

        spec = vim.VimClusterVSANStretchedClusterFaultDomainConfig(
            firstFdHosts=first_fd_host,
            firstFdName=self.prefered_fault_domain_name,
            secondFdHosts=second_fd_host,
            secondFdName=self.second_fault_domain_name
        )

        return spec


    def vsan_host_disk_state(self, host, state):
        '''

        '''

        disks = host.config.storageDevice.scsiLun
        vsan_mgr = host.configManager.vsanSystem

        host_vsan_info = {'name': host.name, 'ssd': [], 'hdd': []}

        for disk in disks:
            eligible_disks = vsan_mgr.QueryDisksForVsan(disk.canonicalName)

            for d in eligible_disks:
                if d.state == state and d.disk.ssd:
                    host_vsan_info['ssd'].append(d.disk)
                if d.state == state and (not d.disk.ssd):
                    host_vsan_info['hdd'].append(d.disk)

        return host_vsan_info


    def vsan_host_disk_mapping_spec(self, host):

        disk_info = self.vsan_host_disk_state(host, 'eligible')
        ssd = disk_info['ssd']
        hdd = disk_info['hdd']

        if not ssd or not hdd:
            self.module.fail_json(msg="No eligible disks on host")

        disk_map_spec = vim.VsanHostDiskMapping(ssd=ssd[0], nonSsd=hdd)

        return disk_map_spec


    def vsan_convert_to_stretch(self, fd_config, disk_mapping):

        result = False

        try:
            result = self.vsan_sc_system.VSANVcConvertToStretchedCluster(
                cluster=self.cluster,
                faultDomainConfig=fd_config,
                witnessHost=self.witness_host,
                preferredFd=self.prefered_fault_domain_name,
                diskMapping=disk_mapping
            )
            WaitForTasks([result], self.si)
        except Exception:
            pass

        return result


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            witness_host=dict(type='dict'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vsan = VsanStretchCluster(module)
    vsan.vsan_process_state()


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *
from ansible.module_utils.vsanapiutils import *
from ansible.module_utils.vsanmgmtObjects import *

if __name__ == '__main__':
    main()