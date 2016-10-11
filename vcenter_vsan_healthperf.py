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
module: vcener_vsan_healthperf
Short_description: Creates (enables) Deletes (disables), Performance Health system for a vsan
    cluster
description:
    Creates (enables) Deletes (disables), Performance Health system for a vsan cluster
requirements:
    - pyvmomi 6
    - vsan SDK
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
    cluster_name:
        description:
            - The name of the vCenter cluster
        required: True
    state:
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: VSAN Config Perf Health
  vcenter_vsan_healtperf:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    datacenter_name: "{{ datacenter.name }}"
    cluster_name: "{{ item.name }}"
    state: 'present'
  with_items:
    - "{{ datacenter.clusters }}"
  tags:
    - vsan_perf_health
'''


try:
    from pyVim import vim, vmodl, connect
    import requests
    import ssl
    import atexit
    import time
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


class VsanHealthPerf(object):
    '''

    '''
    def __init__(self, module):
        self.module = module
        self.cluster_name = module.params['cluster_name']
        self.datacenter_name = module.params['datacenter_name']
        self.cluster = None
        self.datacenter = None
        self.si = None
        self.content = None
        self.vc_mos = None


    def state_exit_unchanged(self):
        self.module.exit_json(changed=False, msg="EXIT UNCHANGED")


    def state_destroy_health_perf(self, vsan_perf_system):
        try:
            deleted_stats = vsan_perf_system.VsanPerfDeleteStatsObject(self.cluster)
        except vim.fault.NotFound:
            self.state_exit_unchanged()
        except (vmodl.RuntimeFault, vim.fault.VsanFault, vmodl.MethodFault):
            self.module.fail_json(msg="Failed to create stats")

        self.module.exit_json(changed=deleted_stats, result=deleted_stats)


    def vsan_health_perf_create(self, vsan_perf_system):
        try:
            result = vsan_perf_system.CreateStatsObject(self.cluster)
        except vim.fault.FileAlreadyExists:
            self.state_exit_unchanged()
        except vim.fault.FileNotFound as fnf:
            self.module.fail_json(msg="File not found: {}".format(str(fnf)))
        except vim.fault.CannotCreateFile as cnc:
            self.module.fail_json(msg="Cannot Create: {}".format(str(cnc)))
        except vim.fault.VsanFault as vf:
            self.module.fail_json(msg="vsan fault: {}".format(str(vf)))
        except (vmodl.RuntimeFault, vmodl.MethodFault):
            self.module.fail_json(msg="Runtime Method fault")

        self.module.exit_json(changed=True, result=result)


    def vsan_health_perf(self):

        self.si = self.connect_to_vc_api()
        self.content = self.si.RetrieveContent()
        self.vc_mos = GetVsanVcMos(self.si._stub, context=None)

        try:
            self.datacenter = find_datacenter_by_name(self.content, self.datacenter_name)

            if not self.datacenter:
                self.module.fail_json(msg="Cannot find DC")

            self.cluster = find_cluster_by_name_datacenter(self.datacenter, self.cluster_name)

            if not self.cluster:
                self.module.fail_json(msg="Cannot find cluster")

        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg=runtime_fault.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

        vsan_perf_system = self.vc_mos['vsan-performance-manager']

        if self.module.params['state'] == 'present':
            self.vsan_health_perf_create(vsan_perf_system)

        if self.module.params['state'] == 'absent':
            self.state_destroy_health_perf(vsan_perf_system)



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


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vsan_health_perf = VsanHealthPerf(module)
    vsan_health_perf.vsan_health_perf()


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *
from ansible.module_utils.vsanapiutils import *
from ansible.module_utils.vsanmgmtObjects import *

if __name__ == '__main__':
    main()