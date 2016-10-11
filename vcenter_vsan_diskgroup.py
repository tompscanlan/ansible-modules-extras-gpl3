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
module: vcener_vsan
Short_description: Creates, deletes hybrid disk groups for a vcenter cluster.
description:
    Creates disk groups for a vcenter cluster. VSAN must be enabled and each host in the cluster
    must have the same disk profile. The disk profile is the number of diskgroups per host
    and the number of hdd disks per disk group.
requirements:
    - pyvmomi 6
    - specified number of disks are eligible
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
            - The name of the vCenter cluster to create the disk groups in
        required: True

    host_disk_profile:
        description:
            - A dict of the disk profile for the cluster. Specifies the number of diskgroups and the number
              of hdd disks per group for each host in the cluster
            - num_disk_groups:
                The number of disk groups per host, also the number of ssd drives
                per host since 1 ssd per diskgroup for cache tier is needed
            - num_disks_per_group:
                The number of hdd disks per disk group.
        type: dict
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True

'''

EXAMPLE = '''
- name: VSAN Config Create Diskgroups
  vcenter_vsan:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    datacenter_name: "{{ datacenter.name }}"
    cluster_name: "{{ item.name }}"
    host_disk_profile:
      num_disk_groups: "{{ item.vsan.num_disk_groups }}"
      num_disks_per_group: "{{ item.vsan.num_disks_per_group }}"
    state: "{{ global_state }}"
  with_items:
    - "{{ datacenter.clusters }}"
  tags:
    - vsan_disk_groups
'''




try:
    from pyVim import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


class VsanHybridDiskgroup(object):
    '''

    '''

    def __init__(self, module):
        self.module = module
        self.cluster_name = module.params['cluster_name']
        self.datacenter_name = module.params['datacenter_name']
        self.cluster = None
        self.datacenter = None
        self.host_list = None
        self.host_vsan_vmk = None
        self.content = connect_to_api(module)
        self.host_disk_profile = module.params['host_disk_profile']
        self.host_disk_ssd = int(module.params['host_disk_profile']['num_disk_groups'])
        self.host_disk_hdd_group = int(module.params['host_disk_profile']['num_disks_per_group'])


    def _fail(self, fail_msg):
        '''
        change ansible loging
        :return:
        '''
        self.module.fail_json(msg=fail_msg)


    def vsan_process_state(self):
        '''
        Given desired state and current state process accordingly
        :return: changed, result
        '''

        vsan_states = {
            'absent': {
                'absent': self.state_exit_unchanged,
                'present': self.state_destroy_diskgroup,
            },
            'present': {
                'absent': self.state_create_diskgroup,
                'present': self.state_exit_unchanged,
            }
        }

        desired_state = self.module.params['state']
        current_state = self.current_state_vsan()

        vsan_states[desired_state][current_state]()


    def state_create_diskgroup(self):
        '''
        Creates disk group for list of specified hosts
        :return:
        '''
        hosts_results = {}

        for host in self.host_list:

            hosts_results.update({host.name: {}})
            host_disk_check = self.vsan_host_check_disk_profile(host)
            hosts_results[host.name].update({'host_disk_check': host_disk_check})

            host_vmks = self.host_vmk_for_vsan(host)
            hosts_results[host.name].update({'host_vsan_vmk': host_vmks})

            if not host_vmks:
                self.module.fail_json(msg="No valid vmks found")

            mcast_spec = self.vsan_host_configinfo_mcast_spec(host_vmks)
            changed, result = self.vsan_host_update_multicast(host, mcast_spec)
            hosts_results[host.name].update({'mcast_spec_update': changed})

            initialize_disk_spec = self.vsan_host_disk_mapping_spec(host, 'eligible')
            changed, result = self.vsan_create_disk_group(host, initialize_disk_spec)
            hosts_results[host.name].update({'create_disk_groups': [changed]})


        self.module.exit_json(changed=True, result=hosts_results, msg='CREATE')


    def state_destroy_diskgroup(self):
        '''
        Destroys diskgroups
        :return:
        '''
        #inverse of hostlist

        hosts = [h for h in self.cluster.host]
        disk_state = 'inUse'

        host_results = {}

        for host in hosts:
            host_results.update({host.name: {}})
            disk_specs = self.vsan_host_disk_mapping_spec(host, disk_state)

            remove_task = self.vsan_delete_disk_group(host, disk_specs)
            #changed, result = wait_for_task(remove_task)

            #host_results[host.name].update({'changed': changed})

        self.module.exit_json(changed=True, result=host_results, msg='DESTROY')


    def state_update_diskgroup(self):
        '''
        Updates diskgroups
        :return:
        '''
        self.module.exit_json(changed=False, msg='UPDATE')


    def state_exit_unchanged(self):
        '''
        No changes made
        :return:
        '''
        self.module.exit_json(changed=False, msg='EXIT UNCHANGED')


    def current_state_vsan(self):

        state = 'absent'

        try:
            self.datacenter = find_datacenter_by_name(self.content, self.datacenter_name)

            if not self.datacenter:
                self.module.fail_json(msg="Cannot find DC")

            self.cluster = find_cluster_by_name_datacenter(self.datacenter, self.cluster_name)

            if not self.cluster:
                self.module.fail_json(msg="Cannot find cluster")

            self.host_list = [host for host in self.cluster.host if not host.config.vsanHostConfig.storageInfo.diskMapping]

            for host in self.cluster.host:
                hosts_disk_groups = len(host.config.vsanHostConfig.storageInfo.diskMapping)
                if hosts_disk_groups < self.host_disk_ssd and host not in self.host_list:
                    self.host_list.append(host)

            if not self.host_list:
                state = 'present'


        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg=runtime_fault.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

        return state


    def host_vmk_for_vsan(self, host):
        '''
        Gets hosts vmk with servicetype vsan
        :return: str, vmk
        '''
        try:
            query_vsan = host.configManager.virtualNicManager.QueryNetConfig('vsan')
        except Exception:
            query_vsan = None

        if not query_vsan.selectedVnic:
            return None

        selected_vmks = [i for i in query_vsan.selectedVnic]

        vsan_vmks = [v.device for v in query_vsan.candidateVnic if v.key in selected_vmks]

        if not vsan_vmks:
            return None

        return vsan_vmks


    def vsan_host_configinfo_mcast_spec(self, vmks):
        '''
        Returns vim.vsan.host.ConfigInfo()
        The vim.vsan.host.ConfigInfo() spec is used for setting vsan multicast addr,
        use this spec with the method multicast_spec_update()
        upstream and downstream values are hard coded defaults for this spec
        :return:
        '''
        config_info = vim.vsan.host.ConfigInfo()
        config_info_net = vim.vsan.host.ConfigInfo.NetworkInfo()

        for vmk in vmks:
            port_config_info = vim.vsan.host.ConfigInfo.NetworkInfo.PortConfig()
            port_config_info.device = vmk
            port_config_info.ipConfig = vim.vsan.host.IpConfig(
                upstreamIpAddress="224.1.2.3",
                downstreamIpAddress="224.2.3.4"
            )
            config_info_net.port.append(port_config_info)

        config_info.networkInfo = config_info_net

        return config_info


    def vsan_host_update_multicast(self, host, spec):

        changed = False
        result = None

        vsan_manager = host.configManager.vsanSystem

        try:
            update_mcast = vsan_manager.UpdateVsan_Task(spec)
            changed, result = wait_for_task(update_mcast)
        except Exception:
            pass

        return changed, result


    def vsan_host_check_disk_profile(self, host):
        '''
        Returns bool, true if eligible disks meet desired self.host_disk_profile
        :return: bool
        '''
        state = True
        disk_info = self.vsan_host_disk_state(host, 'eligible')

        if not disk_info['ssd'] or not disk_info['hdd']:
            state = False
        if len(disk_info['ssd']) < self.host_disk_ssd:
            state = False
        if self.host_disk_hdd_group * self.host_disk_ssd < len(disk_info['hdd']):
            state = False

        return state


    def vsan_host_disk_state(self, host, state):
        '''
        Returns dict of host ssd and hdd disks with given state for vsan
        :param host: vim.HostSystem()
        :param state: eligible, ineligible, inUse
        :return: dict, host_vsan_info
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


    def vsan_host_disk_mapping_spec(self, host, disk_state):

        disk_info = self.vsan_host_disk_state(host, disk_state)
        ssd = disk_info['ssd']
        hdd = disk_info['hdd']

        hdd_progress = {}
        for h in hdd:
            hdd_progress.update({h:'available'})

        init_disk_specs = {}

        for i in range(len(ssd)):
            init_disk_specs[i] = vim.vsan.host.DiskMapping()
            init_disk_specs[i].ssd = ssd[i]

            for x, item in enumerate(hdd):
                if hdd_progress[item] == 'available':
                    init_disk_specs[i].nonSsd.append(item)
                    hdd_progress[item] = 'used'
                if len(init_disk_specs[i].nonSsd) == self.host_disk_hdd_group:
                    break

        specs = [v for k, v in init_disk_specs.items()]

        return specs


    def vsan_create_disk_group(self, host, spec_list):

        changed = False
        result = None

        vsan_mgr = host.configManager.vsanSystem

        try:
            init_disks_task = vsan_mgr.InitializeDisks_Task(spec_list)
            changed, result = wait_for_task(init_disks_task)
        except Exception:
            pass

        return changed, result


    def vsan_delete_disk_group(self, host, spec_list):
        changed = False
        result = None

        vsan_mgr = host.configManager.vsanSystem

        try:
            delete_disks_task = vsan_mgr.RemoveDiskMapping_Task(spec_list)
            changed, result = wait_for_task(delete_disks_task)
        except Exception:
            pass

        return changed, result



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            host_disk_profile=dict(type='dict'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vsan = VsanHybridDiskgroup(module)
    vsan.vsan_process_state()

from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()