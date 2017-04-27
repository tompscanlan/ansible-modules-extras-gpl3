#!/usr/bin/python
# coding=utf-8
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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: vio_oms_deploy
Short_description: Deploys (creates), Deletes vio vapp to vcenter
description:
    Module will deploy and delete vio vapp from vcenter
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
    - VIO 3.0
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
    vmname:
        description:
            - The name of the vm in vcenter
        required: True
    ovftool_path:
        description:
            - The path where the ovftool is installed
        ex: /usr/local/bin/ovftool
    path_to_ova:
        description:
            - The path where the ova is located
        required: True
    ova_file:
        description:
            - The name of the ova file
        required: True
    disk_mode:
        description:
            - The disk mode for the deployment of the ova
        default: thin
        required: True
    datastore:
        description:
            - Valid vcenter datastore
        required: True
    network:
        description:
            - Name of the network/portgroup for the appliance
        required: True
    viouser_password:
        description:
            - password for the vio user
        required: True
    oms_hostname:
        description:
            - hostname for the oms server
        required: True
    oms_ip:
        description:
            - ip address for the oms server
        required: True
    oms_subnet:
        description:
            - subnet for the oms server
        required: True
    oms_gateway:
        description:
            - gatway information for the oms server
        required: True
    oms_dns_server_ip:
        description:
            - list of dns servers
        type: list
        required: True
    oms_search_path:
        description:
            - domain search path for oms server
        required: True
    oms_ntp_server:
        description:
            - NTP Server for synchronizing the VIO Management Server time
        required: True
    oms_syslog_server:
        description:
            - syslog server for the oms to use
        required: True
    oms_syslog_protocol:
        description:
            - Protocol used by syslog server to upload logs
        required: True
    oms_syslog_port:
        description:
            - Syslog Server Port
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True

'''

EXAMPLES = '''
- name: Deploy OMS vAPP
  vio_oms_deploy:
    hostname: "{{ vio_oms_vcenter_hostname }}"
    username: "{{ vio_oms_vcenter_username }}"
    password: "{{ vio_oms_vcenter_pwd }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    vmname: "{{ oms_vm_name }}"
    ovftool_path: "{{ ovf_tool_path }}"
    path_to_ova: "{{ vio_ova_path }}"
    ova_file: "{{ vio_ova }}"
    datacenter: "{{ vio_oms_datacenter_name }}"
    cluster: "{{ vio_oms_cluster_name }}"
    disk_mode: "{{ oms_disk_mode }}"
    datastore: "{{ vio_oms_datastore }}"
    network: "{{ vio_oms_network }}"
    viouser_password: "{{ viouser_pwd }}"
    oms_hostname: "{{ oms_hostname }}"
    oms_ip: "{{ vio_oms_ip_address }}"
    oms_subnet: "{{ vio_oms_ip_subnet }}"
    oms_gateway: "{{ vio_oms_ip_gw}}"
    oms_dns_server_ip: "{{ oms_dns_list }}"
    oms_search_path: "{{ dns_domain_name }}"
    oms_ntp_server: "{{ ntp_server }}"
    oms_syslog_server: "{{ syslog_server }}"
    oms_syslog_protocol: "{{ vio_oms_syslog_protocol }}"
    oms_syslog_port: "{{ vio_oms_syslog_port }}"
    state: "{{ desired_state }}"
  register: oms_deploy
  tags:
    - deploy_vio_ova
'''

RETURN = '''
power_state:
  description: 
    state of the vapp power
  type: bool
api_status:
  description:
    api status of vapp
  type: bool
object_id:
  description:
    moId id for the vapp
  type: str
'''

try:
    import time
    import requests
    from pyVmomi import vim, vmodl
    IMPORTS = True
except ImportError:
    IMPORTS = False

vc = {}

def check_oms_api(module):
    url = "https://{}:8443/oms/api/hello".format(module.params['oms_ip'])
    try:
        resp = requests.get(url=url, verify=False)
    except requests.exceptions.ConnectionError:
        return False
    return resp.status_code, resp.content

def wait_for_api(module, sleep_time=15):
    status_poll_count = 0
    while status_poll_count < 30:
        api_status = check_oms_api(module)
        if api_status:
            if api_status[0] == 200:
                return True
            else:
                status_poll_count += 1
                time.sleep(sleep_time)
        else:
            status_poll_count += 1
            time.sleep(sleep_time)

        if status_poll_count == 30:
            return False

def wait_for_vm(vm, sleep_time=15):
    vm_pool_count = 0
    while vm_pool_count < 30:

        connected = (vm.runtime.connectionState == 'connected')

        if connected:
            powered_on = (vm.runtime.powerState == 'poweredOn')

            if powered_on:
                return True
            else:
                vm_pool_count += 1
                time.sleep(sleep_time)
        else:
            vm_pool_count += 1
            time.sleep(sleep_time)

        if vm_pool_count == 30:
            return False

def find_virtual_machine(content, searched_vm_name):
    virtual_machines = get_all_objs(content, [vim.VirtualMachine])
    for vm in virtual_machines:
        if vm.name == searched_vm_name:
            return vm
    return None

def get_all_objs(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj

def find_vcenter_object_by_name(content, vimtype, name):
    objts = get_all_objs(content, [vimtype])
    for objt in objts:
        if objt.name == name:
            return objt
    return None

def get_resgroup(content, name):
    resgroup = find_vcenter_object_by_name(content, vim.VirtualApp, name)
    return resgroup

def get_vapp_data():
    vapp = vc['oms_vapp']
    vapp_data = {}
    vapp_data.update({'id': vapp._moId})
    vapp_data.update({'name': vapp.name})
    return vapp_data

def state_delete_vapp(module):
    vapp = vc['oms_vapp']
    vapp_data = get_vapp_data()

    power_off = vapp.PowerOffVApp_Task(True)
    wait_for_task(power_off)

    delete_vapp = vapp.Destroy_Task()
    changed, result = wait_for_task(delete_vapp)

    module.exit_json(changed=changed, object_id=vapp_data['id'], object_name=vapp_data['name'], msg="STATE DELETE")

def state_exit_unchanged(module):
    vapp_id = None
    vapp_name = None

    if module.params['state'] != 'absent':
        vapp_data = get_vapp_data()
        vapp_id = vapp_data['id']
        vapp_name = vapp_data['name']

    module.exit_json(changed=False, object_id=vapp_id, object_name=vapp_name, msg="EXIT UNCHANED")

def state_create_vapp(module):
    ovftool_exec = '{}/ovftool'.format(module.params['ovftool_path'])
    ova_file = '{}/{}'.format(module.params['path_to_ova'], module.params['ova_file'])
    vi_string = 'vi://{}:{}@{}/{}/host/{}/'.format(module.params['username'],
                                                   module.params['password'], module.params['hostname'],
                                                   module.params['datacenter'], module.params['cluster'])

    ova_tool_result = module.run_command([ovftool_exec,
                                          '--acceptAllEulas',
                                          '--skipManifestCheck',
                                          '--powerOn',
                                          '--noSSLVerify',
                                          '--allowExtraConfig',
                                          '--vService:installation=com.vmware.vim.vsm:extension_vservice',
                                          '--diskMode={}'.format(module.params['disk_mode']),
                                          '--datastore={}'.format(module.params['datastore']),
                                          '--network={}'.format(module.params['network']),
                                          '--name={}'.format(module.params['vmname']),
                                          '--prop:viouser_passwd={}'.format(module.params['viouser_password']),
                                          '--prop:vami.domain.management-server={}'.format(module.params['oms_hostname']),
                                          '--prop:vami.ip0.management-server={}'.format(module.params['oms_ip']),
                                          '--prop:vami.netmask0.management-server={}'.format(module.params['oms_subnet']),
                                          '--prop:vami.gateway.management-server={}'.format(module.params['oms_gateway']),
                                          '--prop:vami.DNS.management-server={},{}'.format(module.params['oms_dns_server_ip'][0],
                                                                                           module.params['oms_dns_server_ip'][1]),
                                          '--prop:vami.searchpath.management-server={}'.format(module.params['oms_search_path']),
                                          '--prop:ntpServer={}'.format(module.params['oms_ntp_server']),
                                          '--prop:syslogServer={}'.format(module.params['oms_syslog_server']),
                                          '--prop:syslogProtocol={}'.format(module.params['oms_syslog_protocol']),
                                          '--prop:syslogPort={}'.format(module.params['oms_syslog_port']),
                                          ova_file,
                                          vi_string])

    if ova_tool_result[0] != 0:
        msg = 'Failed to deploy OVA, error message from ovftool is: {}'.format(ova_tool_result[1])
        module.fail_json(msg=msg)
    return ova_tool_result[0]



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            vmname=dict(required=True, type='str'),
            ovftool_path=dict(required=True, type='str'),
            path_to_ova=dict(required=True, type='str'),
            ova_file=dict(required=True, type='str'),
            datacenter=dict(required=True, type='str'),
            cluster=dict(required=True, type='str'),
            disk_mode=dict(default='thin', type='str'),
            datastore=dict(required=True, type='str'),
            network=dict(required=True, type='str'),
            viouser_password=dict(required=True, no_log=True, type='str'),
            oms_hostname=dict(required=True, type='str'),
            oms_ip=dict(required=True, type='str'),
            oms_subnet=dict(required=True, type='str'),
            oms_gateway=dict(required=True, type='str'),
            oms_dns_server_ip=dict(required=True, type='list'),
            oms_search_path=dict(required=True, type='str'),
            oms_ntp_server=dict(required=True, type='str'),
            oms_syslog_server=dict(required=True, type='str'),
            oms_syslog_protocol=dict(required=True, type='str'),
            oms_syslog_port=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent']),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    content = connect_to_api(module)

    oms_vapp = get_resgroup(content, module.params['vmname'])

    vc['oms_vapp'] = oms_vapp

    oms_vapp_states = {
        'absent': {
            'present': state_delete_vapp,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_vapp
        }
    }

    desired_state = module.params['state']

    if oms_vapp:
        current_state = 'present'
    else:
        current_state = 'absent'

    oms_vapp_states[desired_state][current_state](module)

    oms_mgmt_svr = find_virtual_machine(content, 'management-server')

    if not oms_mgmt_svr:
        msg = "Failed to find oms management server"
        module.fail_json(msg=msg)

    if not wait_for_vm(oms_mgmt_svr):
        msg = "Failed waiting to power on management server"
        module.fail_json(msg=msg)

    if not wait_for_api(module):
        msg = "Failed waiting for OMS api"
        module.fail_json(msg=msg)

    module.exit_json(changed=True,
                     power_state=True,
                     api_status=True,
                     object_id=oms_mgmt_svr._moId)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
