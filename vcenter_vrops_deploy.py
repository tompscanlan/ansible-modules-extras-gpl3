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
module: vcenter_vrops_deploy
Short_description: Deploys (creates), Deletes vROps ova to vcenter cluster
description:
    Deploys (creates), Deletes vROps ova to vcenter cluster. Module will wait for vm to
    power on.
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
    - vRealize-Operations-Manager-Appliance-6.2.1.3774215_OVF10.ova
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
    gateway:
        description:
            - gatway information for the appliance
        required: True
    dns_ip:
        description:
            - dns server ip address
        type: list
    ip_addr:
        description:
            - ip address for the appliance
        required: True
    netmask:
        description:
            - netmask information for the appliance
        required: True
    deployment_size:
        description:
            - size of the deployment for the appliance
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: deploy vROPs Appliance
  vcenter_vrops_deploy:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    vmname: "{{ vrops_vmname }}"
    ovftool_path: "{{ ovf_tool_path }}"
    path_to_ova: "{{ ova_path }}"
    ova_file: "{{ vrops_ova }}"
    datacenter: "{{ datacenter.name }}"
    cluster: "{{ ib_vcenter_mgmt_esx_cluster_name }}"
    disk_mode: "{{ disk_mode }}"
    datastore: "{{ ib_vcenter_mgmt_esx_cluster_name }}_VSAN_DS"
    network: "{{ mgmt_vds_viomgmt }}"
    time_zone: "{{ vrops_time_zone }}"
    gateway: "{{ vrops_gateway }}"
    dns_ip: "{{ ova_dns_list }}"
    ip_addr: "{{ vrops_ip_addr }}"
    netmask: "{{ vrops_netmask }}"
    ip_protocol: "IPv4"
    deployment_size: "{{ vrops_deploy_size }}"
    state: "{{ global_state }}"
  tags:
    - vio_deploy_vrops_ova
'''


try:
    import time
    import requests
    from pyVmomi import vim, vmodl
    IMPORTS = True
except ImportError:
    IMPORTS = False

vc = {}

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

    vm = vc['vrops_vm']

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
                                          '--X:enableHiddenProperties',
                                          '--diskMode={}'.format(module.params['disk_mode']),
                                          '--datastore={}'.format(module.params['datastore']),
                                          '--network={}'.format(module.params['network']),
                                          '--name={}'.format(module.params['vmname']),
                                          '--deploymentOption={}'.format(module.params['deployment_size']),
                                          '--prop:forceIpv6={}'.format(False),
                                          '--prop:vamitimezone={}'.format(module.params['time_zone']),
                                          '--prop:vami.gateway.vRealize_Operations_Manager_Appliance={}'.format(module.params['gateway']),
                                          '--prop:vami.DNS.vRealize_Operations_Manager_Appliance={},{}'.format(module.params['dns_ip'][0],
                                                                                                            module.params['dns_ip'][1]),
                                          '--prop:vami.ip0.vRealize_Operations_Manager_Appliance={}'.format(module.params['ip_addr']),
                                          '--prop:vami.netmask0.vRealize_Operations_Manager_Appliance={}'.format(module.params['netmask']),
                                          '--prop:guestinfo.cis.appliance.ssh.enabled={}'.format(True),
                                          '--ipProtocol={}'.format(module.params['ip_protocol']),
                                          ova_file,
                                          vi_string])

    if ova_tool_result[0] != 0:
        module.fail_json(msg='Failed to deploy OVA, error message from ovftool is: {}'.format(ova_tool_result[1]))

    module.exit_json(changed=True, result=ova_tool_result[0])



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
            time_zone=dict(required=True, type='str'),
            gateway=dict(required=True, type='str'),
            dns_ip=dict(required=True, type='list'),
            ip_addr=dict(required=True, type='str'),
            netmask=dict(required=True, type='str'),
            ip_protocol=dict(type='str', default="IPv4"),
            deployment_size=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent']),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    content = connect_to_api(module)

    vrops_vm = find_virtual_machine(content, module.params['vmname'])

    vc['vrops_vm'] = vrops_vm

    vrops_vm_states = {
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

    if vrops_vm:
        current_state = 'present'
    else:
        current_state = 'absent'

    vrops_vm_states[desired_state][current_state](module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
