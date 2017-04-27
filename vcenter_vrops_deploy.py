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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
module: vcenter_vrops_deploy
Short_description: Deploys (creates), Deletes vROPs ova to vcenter cluster
description:
    Deploys, Deletes vROPs ova to vcenter cluster. Module will wait for vm to
    power on and "pings" the vROPs api before exiting if not failed.
requirements:
    - pyvmomi 6
    - ansible 2.x
    - requests
    - time
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
    - VMware-*.ova
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

    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: vROPs ova
  vcenter_vrops_deploy:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    datacenter: "{{ _vrops_datacenter }}"
    cluster: "{{ _vrops_cluster }}"
    vmname: "{{ item.vm_name }}"
    datastore: "{{ item.vm_datastore }}"
    disk_mode: "{{ item.vm_disk_mode }}"
    network: "{{ item.vm_network }}"
    ip_protocol: "{{ item.vm_ip_protocol }}"
    gateway: "{{ item.vm_gateway }}"
    dns_server: "{{ item.vm_dns_server }}"
    ip_address: "{{ item.vm_ip_address }}"
    netmask: "{{ item.vm_netmask }}"
    deployment_size: "{{ item.vm_deployment_size }}"
    enable_ssh: "{{ item.vm_enable_ssh }}"
    state: "{{ global_state }}"
  register: vrops_deploy
  with_items:
    - "{{ vrops_deployments }}"
  tags:
    - deploy_vrops_ova
'''

RETURN = '''
description: 
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


class VropsDeploy(object):
    """Create Read and Delete vrops ova
    """
    def __init__(self, module):
        """Connect to vsphere api initialize
        vsphere object names

        :param module: AnsibleModule
        :param name: Module Parameter name of vm
        :param datacenter_name: Module Parameter
        :param cluster_name: Module Parameter
        :param datastore_name: Module Parameter
        :param network_name: Module Parameter
        :param si: vsphere ServiceInstance
        """
        super(VropsDeploy, self).__init__()
        self.module          = module
        self.si              = connect_to_api(module)
        self.name            = module.params['vmname']
        self.datacenter_name = module.params['datacenter']
        self.cluster_name    = module.params['cluster']
        self.datastore_name  = module.params['datastore']
        self.network_name    = module.params['network']
        self.vm              = None

    def _fail(self, msg=None):
        """Fail from AnsibleModule
        :param msg: defaults to None
        """
        if not msg: msg = "General Error occured"
        self.module.fail_json(msg=msg)

    def state_exit_unchanged(self):
        """Returns changed result and msg"""
        changed = False
        result = None
        msg = "EXIT UNCHANGED"
        return changed, result, msg

    def state_delete(self):
        """Returns changed result msg"""
        changed = False
        result = None
        msg = "STATE DELETE"

        if self.vm.runtime.powerState == 'poweredOn':
            power_off_task = self.vm.PowerOffVM_Task()
            wait_for_task(power_off_task)

        try:
            delete_vm_task = self.vm.Destroy_Task()
            changed, result = wait_for_task(delete_vm_task)
        except Exception as e:
            msg = "Failed to Delete VM: {}".format(str(e))
            self._fail(msg)

        return changed, result, msg

    def state_create(self):
        """Returns changed result and msg"""
        changed = False
        result = None
        msg = "STATE CREATE"

        ova_deploy = self.deploy_ova()

        self.vm = self.get_vm(self.name)
        result = {'name': self.vm.name,
                  'moId': self.vm._moId}

        if not self.power_state_wait(self.vm):
            msg = "Failed to wait for power on"
            return changed, result, msg

        if not self.wait_for_api():
            msg = "Failed waiting on api"
            return changed, result, msg

        return True, result, msg

    def run_state(self):
        """Exit AnsibleModule after running state"""
        changed = False
        result = None
        msg = None

        desired_state = self.module.params['state']

        current_state = self.check_state()
        module_state = (desired_state == current_state)

        if module_state:
            changed, result, msg = self.state_exit_unchanged()

        if desired_state == 'absent' and current_state == 'present':
            changed, result, msg = self.state_delete()

        if desired_state == 'present' and current_state == 'absent':
            changed, result, msg = self.state_create()

        self.module.exit_json(changed=changed, result=result, msg=msg)

    def get_vm(self, vm_name):
        vm = find_vm_by_name(self.si, vm_name)
        return vm

    def deploy_ova(self):

        ovftool_exec = '{}/ovftool'.format(self.module.params['ovftool_path'])
        ova_file = '{}/{}'.format(self.module.params['path_to_ova'], self.module.params['ova_file'])
        vi_string = 'vi://{}:{}@{}/{}/host/{}/'.format(self.module.params['username'],
                                                       self.module.params['password'], self.module.params['hostname'],
                                                       self.datacenter_name, self.cluster_name)

        ova_tool_result = self.module.run_command([ovftool_exec,
                                                  '--acceptAllEulas',
                                                  '--skipManifestCheck',
                                                  '--powerOn',
                                                  '--noSSLVerify',
                                                  '--allowExtraConfig',
                                                  '--X:enableHiddenProperties',
                                                  '--powerOn',
                                                  '--X:logFile={}'.format('/var/log/chaperone/ovftool_log_vrops.log'),
                                                  '--diskMode={}'.format(self.module.params['disk_mode']),
                                                  '--datastore={}'.format(self.datastore_name),
                                                  '--network={}'.format(self.network_name),
                                                  '--name={}'.format(self.name),
                                                  '--ipProtocol={}'.format(self.module.params['ip_protocol']),
                                                  '--deploymentOption={}'.format(self.module.params['deployment_size']),
                                                  '--prop:vami.gateway.vRealize_Operations_Manager_Appliance={}'.format(self.module.params['gateway']),
                                                  '--prop:vami.DNS.vRealize_Operations_Manager_Appliance={}'.format(self.module.params['dns_server']),
                                                  '--prop:vami.ip0.vRealize_Operations_Manager_Appliance={}'.format(self.module.params['ip_address']),
                                                  '--prop:vami.netmask0.vRealize_Operations_Manager_Appliance={}'.format(self.module.params['netmask']),
                                                  '--prop:guestinfo.cis.appliance.ssh.enabled={}'.format(self.module.params['enable_ssh']),
                                                  ova_file,
                                                  vi_string])

        if ova_tool_result[0] != 0:
            self.module.fail_json(msg='Failed to deploy OVA, error message from ovftool is: {}'.format(ova_tool_result[1]))

        return ova_tool_result[0]

    def power_state_wait(self, vm, sleep_time=15):
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

    def check_api(self):
        url = "https://{}".format(self.module.params['ip_address'])
        header = {'Content-Type': 'application/json'}

        try:
            resp = requests.get(url=url, verify=False, headers=header)
        except requests.exceptions.ConnectionError:
            return False

        return resp.status_code

    def wait_for_api(self, sleep_time=15):
        status_poll_count = 0
        while status_poll_count < 30:

            api_status = self.check_api()

            if api_status:
                if api_status == 200:
                    return True
                else:
                    status_poll_count += 1
                    time.sleep(sleep_time)
            else:
                status_poll_count += 1
                time.sleep(sleep_time)

            if status_poll_count == 30:
                return False

    def check_vcenter_objects(self):
        state = False

        datacenter = find_datacenter_by_name(self.si, self.datacenter_name)

        if not datacenter:
            return state

        cluster   = None
        datastore = None

        try:
            cluster = [c for c in datacenter.hostFolder.childEntity if c.name == self.cluster_name][0]
        except IndexError:
            return state

        try:
            datastore = [d for d in cluster.datastore if d.name == self.datastore_name][0]
        except IndexError:
            return state

        return True

    def check_state(self):
        state = 'absent'

        vcenter_dependencies = self.check_vcenter_objects()

        if not vcenter_dependencies:
            msg = "Failed to get vcenter object depenedencies"
            self._fail(msg)

        self.vm = find_vm_by_name(self.si, self.name)

        if self.vm:
            state = 'present'

        return state


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(dict(vmname=dict(required=True, type='str'),
                              datacenter=dict(required=False, type='str'),
                              cluster=dict(required=False, type='str'),
                              datastore=dict(required=False, type='str'),
                              disk_mode=dict(type='str', default='thin'),
                              network=dict(required=True, type='str'),
                              gateway=dict(required=False, type='str'),
                              dns_server=dict(required=False, type='str'),
                              netmask=dict(required=False, type='str'),
                              ip_address=dict(required=False, type='str'),
                              enable_ssh=dict(type='bool', default=True),
                              ip_protocol=dict(type='str', default='IPv4'),
                              deployment_size=dict(default='small',
                                                   choices=['small', 'medium', 'large',
                                                            'smallrc', 'largerc', 'xsmall']),
                              ovftool_path=dict(required=True, type='str'),
                              path_to_ova=dict(required=True, type='str'),
                              ova_file=dict(required=True, type='str'),
                              state=dict(default='present', choices=['present', 'absent']),))

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=False,
                           required_together=[['network', 'gateway', 'dns_server',
                                              'ip_address', 'netmask', 'ip_protocol'],
                                              ['datacenter', 'datastore', 'cluster'],])

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    vrops = VropsDeploy(module)
    vrops.run_state()


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
