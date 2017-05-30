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
module: vcenter_vro_deploy
Short_description: Deploys (creates), Deletes vRO ova to vcenter cluster
description:
    Deploys (creates), Deletes vRO ova to vcenter cluster. Module will wait for vm to
    power on and "pings" the vRO api before exiting if not failed.
requirements:
    - pyvmomi 6
    - ansible 2.x
    - ovftool
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
    - VMware-vCO-Appliance-6.0.3.0-3000579_OVF10.ova
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
    datacenter:
        description:
            - The name of the datacenter.
        required: True
    cluster:
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
    vro_gateway:
        description:
            - gatway information for the appliance
        required: True
    vro_dns_ip:
        description:
            - dns server ip address
        type: list
    vro_ip_address:
        description:
            - ip address for the appliance
        required: True
    vro_netmask:
        description:
            - netmask information for the appliance
        required: True
    root_password:
        description:
            - root password for the appliance
        required: True
    deployment_size:
        description:
            - size of the deployment for the appliance
        required: True
    vro_hostname:
        description:
            - hostname for the appliance
        required: True
    vro_domain:
        description:
            - The domain name for the appliance
        required: True
    enable_ssh:
        description:
            - Enable or disable ssh on appliance
        type: bool
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: deploy vRO Appliance
  vcenter_vro_deploy:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    vmname: "{{ vro_vm_name }}"
    ovftool_path: "{{ ovf_tool_path }}"
    path_to_ova: "{{ ova_path }}"
    ova_file: "{{ vro_ova }}"
    datacenter: "{{ ib_vcenter_datacenter_name }}"
    cluster: "{{ ib_vcenter_mgmt_esx_cluster_name }}"
    disk_mode: "{{ disk_mode }}"
    datastore: "{{ ib_vcenter_mgmt_esx_cluster_name }}_VSAN_DS"
    network: "{{ mgmt_vds_viomgmt }}"
    vro_root_pass: "{{ vro_rootpass }}"
    enable_ssh: True
    vro_hostname: "{{ vro_hostname }}"
    vro_gateway: "{{ vro_gateway }}"
    vro_domain: "{{ vro_domain_name }}"
    vro_dns_ip: "{{ ova_dns_list }}"
    vro_ip_address: "{{ vro_ip }}"
    vro_netmask: "{{ vro_netmask }}"
    state: "{{ global_state }}"
  tags:
    - deploy_vro_ova
'''

RETURN = '''
description: TBD
returned: 
type: 
sample: 
'''

try:
    import time
    import requests
    from pyVmomi import vim, vmodl
    IMPORTS = True
except ImportError:
    IMPORTS = False


vc = {}

def check_vro_api(module):

    url = "https://{}:8281/vco/api/".format(module.params['vro_ip_address'])
    auth = requests.auth.HTTPBasicAuth('vcoadmin','vcoadmin')
    header = {'Content-Type': 'application/json', 'Accept': 'application/json'}

    try:
        resp = requests.get(url=url, verify=False,
                            auth=auth, headers=header)

    except requests.exceptions.ConnectionError:
        return False

    return resp.status_code, resp.content


def wait_for_api(module, sleep_time=15):
    status_poll_count = 0
    while status_poll_count < 30:
        api_status = check_vro_api(module)
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


def state_delete_vm(module):
    changed = False

    vm = vc['vro_vm']

    if vm.runtime.powerState == 'poweredOn':
        power_off_task = vm.PowerOffVM_Task()
        wait_for_task(power_off_task)

    try:
        delete_vm_task = vm.Destroy_Task()
        changed, result = wait_for_task(delete_vm_task)
    except Exception as e:
        module.fail_json(msg="Failed deleting vm: {}".format(str(e)))

    module.exit_json(changed=changed)


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANED")


def state_create_vm(module):

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
                                          '--diskMode={}'.format(module.params['disk_mode']),
                                          '--datastore={}'.format(module.params['datastore']),
                                          '--network={}'.format(module.params['network']),
                                          '--name={}'.format(module.params['vmname']),
                                          '--prop:varoot-password={}'.format(module.params['vro_root_pass']),
                                          '--prop:vcoconf-password={}'.format(module.params['vro_root_pass']),
                                          '--prop:va-ssh-enabled={}'.format(module.params['enable_ssh']),
                                          '--prop:vami.hostname={}'.format(module.params['vro_hostname']),
                                          '--prop:vami.gateway.VMware_vRealize_Orchestrator_Appliance={}'.format(module.params['vro_gateway']),
                                          '--prop:vami.domain.VMware_vRealize_Orchestrator_Appliance={}'.format(module.params['vro_domain']),
                                          '--prop:vami.DSN.VMware_vRealize_Orchestrator_Appliance={},{}'.format(module.params['vro_dns_ip'][0],
                                                                                                                module.params['vro_dns_ip'][1]),
                                          '--prop:vami.ip0.VMware_vRealize_Orchestrator_Appliance={}'.format(module.params['vro_ip_address']),
                                          '--prop:vami.netmask0.VMware_vRealize_Orchestrator_Appliance={}'.format(module.params['vro_netmask']),
                                          ova_file,
                                          vi_string])

    if ova_tool_result[0] != 0:
        module.fail_json(msg='Failed to deploy OVA, error message from ovftool is: {}'.format(ova_tool_result[1]))

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
            vro_root_pass=dict(required=True, type='str', no_log=True),
            enable_ssh=dict(required=True, type='bool'),
            vro_hostname=dict(required=True, type='str'),
            vro_gateway=dict(required=True, type='str'),
            vro_domain=dict(required=True, type='str'),
            vro_dns_ip=dict(required=True, type='list'),
            vro_ip_address=dict(required=True, type='str'),
            vro_netmask=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent']),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    content = connect_to_api(module)

    vro_vm = find_virtual_machine(content, module.params['vmname'])

    vc['vro_vm'] = vro_vm

    vro_vm_states = {
        'absent': {
            'present': state_delete_vm,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_vm
        }
    }

    desired_state = module.params['state']

    if vro_vm:
        current_state = 'present'
    else:
        current_state = 'absent'

    vro_vm_states[desired_state][current_state](module)

    vro_vm = find_virtual_machine(content, module.params['vmname'])

    if not vro_vm:
        module.fail_json(changed=False, msg="Failed to find vm")

    if not wait_for_vm(vro_vm):
        module.fail_json(msg="VM failed to power on")

    if not wait_for_api(module):
        module.fail_json(msg="Failed to hit api")

    module.exit_json(changed=True, result="Success")


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
