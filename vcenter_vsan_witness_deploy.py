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
module: vcener_vsan_witness_deploy
Short_description: Deploys (Creates), Removes (Deletes) a witness host appliance for a stretched cluster
description:
    Deploys (Creates), Removes (Deletes) a witness host appliance for a stretched cluster
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6
    - pyvmomi 6
    - esx 6
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
            - The path where the witness appliance ova is located
        required: True
    ova_file:
        description:
            - The name of the ova file
        ex: VMware-VirtualSAN-Witness-6.x.x.ova
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
    management_network:
        description:
            - Management Network will be used to drive witness vm traffic
        required: True
    vsan_network:
        description:
            - Witness Network will be used to drive witness vm traffic
        required: True
    root_password:
        description:
            - Set password for root account. A valid password must be at least 7 characters long and must
               contain a mix of upper and lower case letters, digits, and other
               characters.  You can use a 7 character long password with characters from at least 3
               of these 4 classes.  An upper case letter that begins the password and a
               digit that ends it do not count towards the number of character classes
               used.
            - module does not validate password
        required: True
    deployment_size:
        description:
            - deployment options
        options:
            - tiny:
                Configuration for Tiny Virtual SAN Deployments with 10 VMs or fewer
            - normal:
                Configuration for Medium Virtual SAN Deployments of up to 500 VMs
            - large:
                Configuration for Large Virtual SAN Deployments of more than 500 VMs
        required: True
    state:
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: deploy vsan witness appliance for edge cluster
  vcenter_vsan_witness_deploy:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    vmname: "{{ wa_vm_name }}"
    ovftool_path: "{{ ovf_tool_path }}"
    path_to_ova: "{{ ova_path }}"
    ova_file: "{{ wa_ova }}"
    datacenter: "{{ datacenter.name }}"
    cluster: "{{ ib_vcenter_mgmt_esx_cluster_name }}"
    disk_mode: "{{ disk_mode }}"
    datastore: "{{ ib_vcenter_mgmt_esx_cluster_name }}_VSAN_DS"
    management_network: "{{ mgmt_vds_viomgmt }}"
    vsan_network: "{{ edge_vsan_pg }}"
    root_password: "{{ wa_root_pass }}"
    deployment_size: "{{ wa_deployment_size }}"
    state: "{{ global_state }}"
  tags:
    - vio_deploy_wa_ova
'''


try:
    import json
    import os
    import requests
    import time
    from pyVmomi import vim, vmodl
    IMPORTS = True
except ImportError:
    IMPORTS = False


class TaskError(Exception):
    pass

vc = {}

def wait_for_vm(vm):
    while True:

        if vm.runtime.powerState == 'poweredOn' and vm.runtime.connectionState == 'connected':
            return True
        if vm.runtime.connectionState in ('inaccessible', 'invalid', 'orphaned') or \
                vm.rumtime.powerState == 'suspended':
            try:
                raise TaskError("VM in Error State")
            except TaskError as e:
                return e

        time.sleep(15)


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


def state_delete_vm(module):

    changed = False

    vm = vc['witness_appliance']

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


def ova_tool_command_list(module, ovftool_exec, ova_file, vi_string, proxy=None):
    ova_command_list = [ovftool_exec,
                        '--acceptAllEulas',
                        '--skipManifestCheck',
                        '--powerOn',
                        '--noSSLVerify',
                        '--allowExtraConfig',
                        '--name={}'.format(module.params['vmname']),
                        '--diskMode={}'.format(module.params['disk_mode']),
                        '--datastore={}'.format(module.params['datastore']),
                        '--net:Management Network={}'.format(module.params['management_network']),
                        '--net:Witness Network={}'.format(module.params['vsan_network']),
                        '--deploymentOption={}'.format(module.params['deployment_size']),
                        '--prop:vsan.witness.root.passwd={}'.format(module.params['root_password'])]

    if proxy:
        ova_command_list.append('--proxy={}'.format(proxy))

    ova_command_list.append(ova_file)
    ova_command_list.append(vi_string)

    return ova_command_list


def state_create_vm(module):

    ovftool_exec = '{}/ovftool'.format(module.params['ovftool_path'])
    ova_file = '{}/{}'.format(module.params['path_to_ova'], module.params['ova_file'])
    vi_string = 'vi://{}:{}@{}/{}/host/{}/'.format(module.params['username'],
                                                   module.params['password'], module.params['hostname'],
                                                   module.params['datacenter'], module.params['cluster'])

    ova_commands = ova_tool_command_list(module, ovftool_exec, ova_file, vi_string)

    ova_tool_result = module.run_command(ova_commands)

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
            management_network=dict(required=True, type='str'),
            vsan_network=dict(required=True, type='str'),
            root_password=dict(required=True, type='str'),
            deployment_size=dict(required=True, choices=['tiny', 'normal', 'large']),
            proxy=dict(require=False, type='str'),
            state=dict(default='present', choices=['present', 'absent']),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    content = connect_to_api(module)

    witness_appliance = find_virtual_machine(content, module.params['vmname'])

    vc['witness_appliance'] = witness_appliance

    vm_states = {
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

    if witness_appliance:
        current_state = 'present'
    else:
        current_state = 'absent'

    vm_states[desired_state][current_state](module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
