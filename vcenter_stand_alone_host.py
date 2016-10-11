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
module: vcener_stand_alone_host
Short_description: Adds a standalone host to a vcenter datacenter
description:
    Adds a standalone host to a vcenter datacenter. Module specifically developed for the purposes
    of adding a standalone host outside of a datacenters vsan clusters. Since the default behavior
    of adding a standalone host from a witness appliance for the witness vmk is dhcp this module
    will update the witness vmk ip information to static with the specified ip address.
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6.0
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
    esx_hostname:
        description:
            - hostname of the esx standalone host to add
        required: True
    esx_username:
        description:
            - username for adding the host, root
        required: True
    esx_password:
        description:
            - password for the specified user
        required: True
    witness_vmk_ip:
        description:
            - IP addresss of the hosts vmk
        required: True
    witness_vmk_subnet:
        description:
            - subnet of the hosts vmk
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True

'''

EXAMPLE = '''
- name: Add Standalone Witness Host
  vcenter_stand_alone_host:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    datacenter_name: "{{ datacenter.name }}"
    esx_hostname: "{{ wa_esx_hostname }}"
    esx_username: "{{ wa_esx_username }}"
    esx_password: "{{ wa_rootpass }}"
    witness_vmk_ip: "{{ wa_vsan_vmk_ip }}"
    witness_vmk_subnet: "{{ wa_vsan_vmk_subnet }}"
    state: "{{ global_state }}"
  tags:
    - vsan_stretch_addhost
'''


try:
    from pyVim import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

class AddStandAloneHost(object):
    '''

    '''

    def __init__(self, module):
        self.module = module
        self.datacenter_name = module.params['datacenter_name']
        self.host_name = module.params['esx_hostname']
        self.host_user = module.params['esx_username']
        self.host_password = module.params['esx_password']
        self.content = connect_to_api(module)
        self.datacenter = None
        self.host = None
        self.host_folder = None


    def process_state(self):

        states = {
            'absent': {
                'absent': self.state_exit_unchanged,
                'present': self.state_delete,
            },
            'present': {
                'absent': self.state_create,
                'present': self.state_exit_unchanged,
                'update': self.state_update,
            }
        }

        desired_state = self.module.params['state']
        current_state = self.current_state()

        states[desired_state][current_state]()


    def state_create(self):

        changed, result = self.add_host()

        if changed:
            host = find_hostsystem_by_name(self.content, self.host_name)

            vmk = self.get_vsan_vmk(host)
            vmk = vmk.device

            changed = self.update_witnesspg_vmk(host, vmk)

        self.module.exit_json(changed=changed, result=str(result))


    def state_update(self):
        vmk = self.get_vsan_vmk(self.host)
        vmk = vmk.device

        changed = self.update_witnesspg_vmk(self.host, vmk)

        self.module.exit_json(changed=changed, result='update vmk')


    def update_witnesspg_vmk(self, host, vsan_vmk):
        changed = False

        vsan_vmk_spec = vim.host.VirtualNic.Specification()
        vsan_vmk_spec.ip = vim.host.IpConfig()
        vsan_vmk_spec.ip.dhcp = False
        vsan_vmk_spec.ip.ipAddress = self.module.params['witness_vmk_ip']
        vsan_vmk_spec.ip.subnetMask = self.module.params['witness_vmk_subnet']

        net_sys = host.configManager.networkSystem

        try:
            net_sys.UpdateVirtualNic(device=vsan_vmk,
                                     nic=vsan_vmk_spec)
            changed = True
        except Exception:
            return changed

        return changed


    def add_host(self):

        host_spec = vim.host.ConnectSpec()
        host_spec.hostName = self.host_name
        host_spec.userName = self.host_user
        host_spec.password = self.host_password
        host_spec.force = True
        host_spec.sslThumbprint = ""
        add_connected = True

        try:
            add_host_task = self.host_folder.AddStandaloneHost_Task(spec=host_spec,
                                                                    addConnected=add_connected)
            changed, result = wait_for_task(add_host_task)
            return changed, result
        except TaskError as add_task_error:
            ssl_verify_fault = add_task_error.args[0]
            host_spec.sslThumbprint = ssl_verify_fault.thumbprint

        add_host_task = self.host_folder.AddStandaloneHost_Task(spec=host_spec,
                                                                addConnected=add_connected)
        changed, result = wait_for_task(add_host_task)
        return changed, result


    def state_exit_unchanged(self):
        self.module.exit_json(changed=False, msg="EXIT UNCHANGED")


    def state_delete(self):
        self.module.exit_json(changed=False, msg="Delete")


    def get_vsan_vmk(self, host):

        try:
            query_result = host.configManager.virtualNicManager.QueryNetConfig('vsan')
        except Exception:
            query_result = None

        if not query_result:
            self.module.fail_json(msg="no vmks with vsan service")

        selected_vmks = [i for i in query_result.selectedVnic]
        vsan_vmk = [v for v in query_result.candidateVnic if v.key in selected_vmks][0]

        return vsan_vmk


    def check_witness_vmk(self):

        vsan_vmk = self.get_vsan_vmk(self.host)

        if vsan_vmk.spec.ip.dhcp:
            return False
        if vsan_vmk.spec.ip.ipAddress == self.module.params['witness_vmk_ip']:
            return True


    def current_state(self):
        state = 'absent'

        try:
            self.datacenter = find_datacenter_by_name(self.content, self.datacenter_name)

            if not self.datacenter:
                self.module.fail_json(msg="Cannot find DC")

            self.host_folder = self.datacenter.hostFolder

            self.host = find_hostsystem_by_name(self.content, self.host_name)

            if self.host:
                check_vmk = self.check_witness_vmk()

                if check_vmk:
                    state = 'present'
                else:
                    state = 'update'

        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg=runtime_fault.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

        return state



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            esx_hostname=dict(required=True, type='str'),
            esx_username=dict(required=False, default='root', type='str'),
            esx_password=dict(required=True, type='str', no_log=True),
            witness_vmk_ip=dict(required=True, type='str'),
            witness_vmk_subnet=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    stand_alone = AddStandAloneHost(module)
    stand_alone.process_state()


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()