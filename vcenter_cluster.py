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
module: vmware_cluster
short_description: Create VMware vSphere Cluster
description:
    - Create VMware vSphere Cluster according to dict spec. Module will set
    default values if only enabled specified as true. Full CRUD operations
    on specified values.
notes:
    requirements:
    - pyVmomi
    - Tested on vcenter 6.0.0 Build 2594327
    - ansible 2.1.0.0
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter
        required: True
    username:
        description:
            - The username of the vSphere vCenter
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter
        required: True
        aliases: ['pass', 'pwd']
    datacenter_name:
        description:
            - The name of the datacenter the cluster will be created in.
        required: True
    cluster_name:
        description:
            - The name of the cluster that will be created
        required: True
    ha:
        description:
            - Dict enabling HA and corresponding specifications
        required: False
        defaults: See ha_defaults
        accepted values:
          enabled: [True, False]
          admissionControlEnabled: [True, False]
          failoverLevel: [int]
          hostMonitoring: ['enabled', 'disabled']
          vmMonitoring: ['vmAndAppMonitoring', 'vmMonitoringOnly', 'vmMonitoringDisabled']
          vmMonitoring_sensitivity: [int, 0-2]
          restartPriority: ['high', 'low', 'medium', 'disabled']
    drs:
        description:
            - Dict enabling DRS and corresponding specifications.
        required: False
        defaults: See drs_defaults
        accepted values:
          enabled: [True, False]
          enableVmBehaviorOverrides: [True, False]
          defaultVmBehavior: ['fullyAutomated', 'partiallyAutomated', 'manual']
          vmotionRate: [int, 1-5]
    vsan:
        description:
            - Dict enabling VSAN and corresponding specifications.
        required: False
        accepted values:
          enabled: [True, False]
          autoClaimStorage: [True, False]
'''

EXAMPLES = '''
- name: Create Clusters
  vcenter_cluster:
    hostname: "{{ vcenter_host }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: False
    datacenter_name: "{{ datacenter_name }}"
    cluster_name: "{{ item['name'] }}"
    ha:
      enabled: True
      admissionControlEnabled: True
      failoverLevel: 1
      hostMonitoring: 'enabled'
      vmMonitoring: 'vmAndAppMonitoring'
      vmMonitoring_sensitivity: 1
      restartPriority: 'high'
    drs:
      enabled: True
      enableVmBehaviorOverrides: True
      defaultVmBehavior: 'fullyAutomated'
      vmotionRate: 3
    vsan:
      enabled: True
      autoClaimStorage: True
    state: 'present'
  with_items:
    - "{{ datacenter['clusters'] }}"
  tags:
    - datacenter
'''


try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

drs_defaults = {
    'defaultVmBehavior': 'fullyAutomated',
    'vmotionRate': 3,
    'enableVmBehaviorOverrides': True
}

ha_defaults = {
    'hostMonitoring': 'enabled',
    'admissionControlEnabled': True,
    'failoverLevel': 1,
    'vmMonitoring': 'vmMonitoringDisabled'
}


def check_null_vals(module, spec_type):
    cluster_info = module.params[spec_type]

    if spec_type == 'drs':
        defaults = drs_defaults
    elif spec_type == 'ha':
        defaults = ha_defaults
    elif spec_type == 'vsan':
        defaults = vsan_defaults

    for k, v in cluster_info.items():
        if v == None:
            cluster_info[k] = defaults[k]


def calc_ha_values(module):
    ha_info = module.params['ha']

    ha_value = ha_info['vmMonitoring_sensitivity']

    if ha_value == 0:
        return 120, 480, 604800
    if ha_value == 1:
        return 60, 240, 86400
    if ha_value == 2:
        return 30, 120, 3600


def ha_vmSettings(module):
    ha_info = module.params['ha']
    failure_interval, min_up_time, max_fail_window = calc_ha_values(module)

    vm_tools_spec = vim.cluster.VmToolsMonitoringSettings(
        enabled=True,
        vmMonitoring=ha_info['vmMonitoring'],
        clusterSettings=True,
        failureInterval=failure_interval,
        minUpTime=min_up_time,
        maxFailures=3,
        maxFailureWindow=max_fail_window,
    )

    default_VmSettings = vim.cluster.DasVmSettings(
        restartPriority=ha_info['restartPriority'],
        isolationResponse=None,
        vmToolsMonitoringSettings=vm_tools_spec
    )

    return default_VmSettings


def configure_ha(module, enable_ha):
    check_null_vals(module, 'ha')

    ha_info = module.params['ha']
    admission_control_enabled = ha_info['admissionControlEnabled']
    failover_level = ha_info['failoverLevel']
    host_monitoring = ha_info['hostMonitoring']
    vm_monitoring = ha_info['vmMonitoring']

    if vm_monitoring in ['vmMonitoringOnly', 'vmAndAppMonitoring']:
        default_vm_settings = ha_vmSettings(module)
    else:
        default_vm_settings = None

    das_config = vim.cluster.DasConfigInfo(
        enabled=enable_ha,
        admissionControlEnabled=admission_control_enabled,
        failoverLevel=failover_level,
        hostMonitoring=host_monitoring,
        vmMonitoring=vm_monitoring,
        defaultVmSettings=default_vm_settings
    )

    return das_config

#need to add check for if drs is false
def configure_drs(module, enable_drs):
    check_null_vals(module, 'drs')

    drs_info = module.params['drs']
    drs_vmbehavior = drs_info['enableVmBehaviorOverrides']
    drs_default_vm_behavior = drs_info['defaultVmBehavior']
    drs_vmotion_rate = drs_info['vmotionRate']

    drs_spec = vim.cluster.DrsConfigInfo(
        enabled=enable_drs,
        enableVmBehaviorOverrides=drs_vmbehavior,
        defaultVmBehavior=drs_default_vm_behavior,
        vmotionRate=drs_vmotion_rate,

    )

    return drs_spec


def configure_vsan(module, enable_vsan):
    vsan_config = vim.vsan.cluster.ConfigInfo(
        enabled=enable_vsan,
        defaultConfig=vim.vsan.cluster.ConfigInfo.HostDefaultInfo(
            autoClaimStorage=module.params['vsan']['autoClaimStorage']
        )
    )

    return vsan_config


def check_spec_vsan(si, module):
    pass


def check_spec_drs(si, module):

    datacenter_name = module.params['datacenter_name']
    datacenter = find_datacenter_by_name(si, datacenter_name)

    cluster_name = module.params['cluster_name']
    cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

    drs_info = module.params['drs']
    desired_drs_spec = configure_drs(module, module.params['drs']['enabled'])
    desired_drs_props = [prop for prop, val in desired_drs_spec._propInfo.items()]

    for i in desired_drs_props:
        val = getattr(cluster.configurationEx.drsConfig, i)
        if i != 'option':
            if val != drs_info[i]:
                return False
    else:
        return True


def check_spec_ha(si, module):

    datacenter_name = module.params['datacenter_name']
    datacenter = find_datacenter_by_name(si, datacenter_name)

    cluster_name = module.params['cluster_name']
    cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

    ha_info = module.params['ha']
    desired_ha_spec = configure_ha(module, True)
    desired_ha_props = [prop for prop, val in desired_ha_spec._propInfo.items()]

    check_prop_vals = [prop for prop in ha_info.iterkeys() if prop in desired_ha_props]

    for i in check_prop_vals:
        val = getattr(cluster.configurationEx.dasConfig, i)
        if val != ha_info[i]:
            return False
    else:
        return True


def state_create_cluster(si, module):

    enable_ha = module.params['ha']['enabled']
    enable_drs = module.params['drs']['enabled']
    enable_vsan = module.params['vsan']['enabled']
    cluster_name = module.params['cluster_name']

    datacenter_name = module.params['datacenter_name']
    datacenter = find_datacenter_by_name(si, datacenter_name)

    try:
        cluster_config_spec = vim.cluster.ConfigSpecEx()
        cluster_config_spec.dasConfig = configure_ha(module, enable_ha)
        cluster_config_spec.drsConfig = configure_drs(module, enable_drs)

        if enable_vsan:
            cluster_config_spec.vsanConfig = configure_vsan(module, enable_vsan)

        if not module.check_mode:
            datacenter.hostFolder.CreateClusterEx(cluster_name, cluster_config_spec)

        module.exit_json(changed=True)

    except vim.fault.DuplicateName:
        module.fail_json(msg="A cluster with the name %s already exists" % cluster_name)
    except vmodl.fault.InvalidArgument:
        module.fail_json(msg="Cluster configuration specification parameter is invalid")
    except vim.fault.InvalidName:
        module.fail_json(msg="%s is an invalid name for a cluster" % cluster_name)
    except vmodl.fault.NotSupported:
        module.fail_json(msg="Trying to create a cluster on an incorrect folder object")
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_destroy_cluster(si, module):

    datacenter_name = module.params['datacenter_name']
    datacenter = find_datacenter_by_name(si, datacenter_name)

    cluster_name = module.params['cluster_name']
    cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

    changed = True
    result = None

    try:
        if not module.check_mode:
            task = cluster.Destroy_Task()
            changed, result = wait_for_task(task)
        module.exit_json(changed=changed, result=result)
    except vim.fault.VimFault as vim_fault:
        module.fail_json(msg=vim_fault.msg)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_exit_unchanged(si, module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def state_update_cluster(si, module):

    datacenter_name = module.params['datacenter_name']
    datacenter = find_datacenter_by_name(si, datacenter_name)

    cluster_name = module.params['cluster_name']
    cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

    cluster_config_spec = vim.cluster.ConfigSpecEx()

    enable_ha = module.params['ha']['enabled']
    enable_drs = module.params['drs']['enabled']
    enable_vsan = module.params['vsan']['enabled']

    changed = True
    result = None

    if enable_ha:
        cluster_config_spec.dasConfig = configure_ha(module, enable_ha)
    if enable_drs:
        cluster_config_spec.drsConfig = configure_drs(module, enable_drs)
    if enable_vsan:
        cluster_config_spec.vsanConfig = configure_vsan(module, enable_vsan)

    try:
        if not module.check_mode:
            task = cluster.ReconfigureComputeResource_Task(cluster_config_spec, True)
            changed, result = wait_for_task(task)
        module.exit_json(changed=changed, result=result)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as task_e:
        module.fail_json(msg=str(task_e))


def check_cluster_configuration(si, module):

    datacenter_name = module.params['datacenter_name']
    cluster_name = module.params['cluster_name']

    state = 'absent'

    try:
        datacenter = find_datacenter_by_name(si, datacenter_name)

        if not datacenter:
            module.fail_json(msg="Datacenter {} does not exist".format(datacenter_name))

        cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

        if cluster:

            if module.params['vsan']['enabled']:
                enable_check = (cluster.configurationEx.vsanConfigInfo.enabled == module.params['vsan']['enabled'])
                auto_claim_check = (
                    cluster.configurationEx.vsanConfigInfo.defaultConfig.autoClaimStorage == module.params['vsan']['autoClaimStorage']
                )
                vsan_check = (enable_check and auto_claim_check)
            else:
                vsan_check = True

            check_list = [
                check_spec_drs(si, module),
                check_spec_ha(si, module),
                vsan_check
            ]

            if False in check_list:
                state = 'update'
            else:
                state = 'present'

    except Exception as e:
        module.fail_json(msg="Failed checking state")

    return state


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(required=True, type='str'),
            cluster_name=dict(required=True, type='str'),
            ha=dict(type='dict'),
            drs=dict(type='dict'),
            vsan=dict(type='dict'),
            state=dict(default='present', choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    states = {
        'absent': {
            'absent': state_exit_unchanged,
            'present': state_destroy_cluster,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_cluster,
            'update': state_update_cluster
        }
    }

    context = connect_to_api(module)

    desired_state = module.params['state']
    current_state = check_cluster_configuration(context, module)

    states[desired_state][current_state](context, module)

from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
