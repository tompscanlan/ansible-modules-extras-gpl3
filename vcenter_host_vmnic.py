#!/usr/bin/python
# -*- coding: utf-8 -*-
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

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
---
module: vcenter_host_vmnic
short_description: Obtains a list of available vmnics for a specified host
description:
  Obtains a list of available vmnics for a specified host
version_added: 2.3
author: VMware
notes:
  - Tested on vsphere 6.0
requirements:
  - PyVmomi
options:
  esxi_hostname:
    description:
      - Host name or ip for the esxi host
    required: True
    type: str

'''

EXAMPLES = '''
- name: Get esxi hosts available vmnics
  vcenter_host_vmnic:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    esxi_hostname: "172.16.78.101"
  register: host_vmnics
'''

RETURN = '''
host_vmnics:
  description:
    - dict with host and list of available vmnics
  returned: host_vmnics
  type: dict
  sample: { host: "esxi.corp.local", vmnics: ['vmnic0', 'vmnic1'] }

'''

try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


class VcenterHostVmnics(object):
    """
    Obtains the available/used vmnics for the specified esx host
    :param module AnsibleModule
    :param esxi_hostname
    :param vcapi
    """
    def __init__(self, module):
        super(VcenterHostVmnics, self).__init__()
        self.module = module
        self.esxi_hostname = module.params['esxi_hostname']
        self.get_type = module.params['obtain']
        self.vcapi = connect_to_api(self.module)
        self.host = None
        self.available_vmnics = []


    def run_state(self):
        if not self.check_state():
            self.module.fail_json(msg="Failed to find host: %s " % self.esxi_hostname)

        host_vmnics = self.get_host_vmnics(self.host)

        if self.get_type == 'available':
            vmnics = self.get_host_available_vmnics(host_vmnics)

        if self.get_type == 'used':
            vmnics = self.get_used_vmnic(self.host)

        host_data = {'host': self.esxi_hostname, 'vmnics': vmnics}

        self.module.exit_json(changed=False, host_vmnics=host_data)

    def get_host_available_vmnics(self, vmnics):
        used_vmnics = self.get_used_vmnic(self.host)

        for vmnic in vmnics:
            if vmnic not in used_vmnics:
                self.available_vmnics.append(vmnic)

        return self.available_vmnics

    def get_host_vmnics(self, host):
        net_config = host.configManager.networkSystem.networkConfig
        vmnics = [pnic.device for pnic in net_config.pnic]
        return vmnics

    def get_vswitch_vmnics(self, host):
        vswitch_vmnics = []

        net_config = self.host.configManager.networkSystem.networkConfig

        if not net_config.vswitch:
            return vswitch_vmnics

        for vswitch in net_config.vswitch:
            for v in vswitch.spec.bridge.nicDevice:
                vswitch_vmnics.append(v)

        return vswitch_vmnics

    def get_proxyswitch_vmnics(self, host):
        proxy_switch_vmnics = []

        net_config = self.host.configManager.networkSystem.networkConfig

        if not net_config.proxySwitch:
            return proxy_switch_vmnics

        for proxy_config in net_config.proxySwitch:
            for p in proxy_config.spec.backing.pnicSpec:
                proxy_switch_vmnics.append(p.pnicDevice)

        return proxy_switch_vmnics

    def get_used_vmnic(self, host):
        vswitch_vmnics = self.get_vswitch_vmnics(host)
        proxy_switch_vmnics = self.get_proxyswitch_vmnics(host)
        return vswitch_vmnics + proxy_switch_vmnics

    def check_state(self):
        host = find_hostsystem_by_name(self.vcapi, self.esxi_hostname)

        if not host:
            return False

        self.host = host

        return True


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(dict(esxi_hostname=dict(type='str', require=True),
                              obtain=dict(type='str',
                                          required=False,
                                          default='available',
                                          choices=['available', 'used']),
                              state=dict(default='present', choices=['present', 'absent'], type='str')))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vcenter_host_vmnics = VcenterHostVmnics(module)
    vcenter_host_vmnics.run_state()


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()