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
module: vds
short_description: virtual distributed switch
description:
    - create update delete virtual distributed switch.
options:
    datacenter_name:
        description:
            - The name of the datacenter the cluster will be created in.
        required: True
    vds_name:
        description:
            - The name of the new vds
    numUplinks:
        description:
            - The number of uplinks for the vds
    numPorts:
        description:
            - The number of ports *
    mtu:
        description:
            - The mtu for the vds. Upstream physical switch must match or more
    discovery_protocol:
        description:
            -
    discovery_operation:
        description:
            -
    productVersion:
        description:
            -
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Create VDS
  vds:
    hostname: '172.16.78.15'
    username: 'administrator@vsphere.local'
    password: 'VMware1!'
    validate_certs: False
    datacenter_name: "test-dc-01"
    vds_name: "vds001"
    numUplinks: 4
    numPorts: 16
    mtu: 9000
    discovery_protocol: 'lldp'
    discovery_operation: 'both'
    productVersion: '6.0.0'
    state: 'present'
'''

try:
    from pyVmomi import vim, vmodl
    from pyVim import connect
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


def find_vcenter_object_by_name(content, vimtype, object_name):
    vcenter_object = get_all_objs(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k
    else:
        return None


def find_vds_by_name(content, vds_name):
    vdSwitches = get_all_objs(content, [vim.dvs.VmwareDistributedVirtualSwitch])
    for vds in vdSwitches:
        if vds_name == vds.name:
            return vds
    return None


def _create_vds_spec(si, update, module):

    vds_name = module.params['vds_name']
    mtu = module.params['mtu']
    discovery_protocol = module.params['discovery_protocol']
    discovery_operation = module.params['discovery_operation']
    productVersion = module.params['productVersion']
    numUplinks = module.params['numUplinks']
    numPorts = module.params['numPorts']

    uplink_port_names = []

    for x in range(int(numUplinks)):
        uplink_port_names.append("%s_Uplink_%d" % (vds_name, x + 1))

    prod_info = vim.dvs.ProductSpec(
        version = productVersion,
        name = "DVS",
        vendor = "VMware, Inc."
    )

    uplink = vim.DistributedVirtualSwitch.NameArrayUplinkPortPolicy(
        uplinkPortName = uplink_port_names
    )

    linkConfig = vim.host.LinkDiscoveryProtocolConfig(
        protocol = discovery_protocol,
        operation = discovery_operation
    )

    configSpec = vim.dvs.VmwareDistributedVirtualSwitch.ConfigSpec(
        name = vds_name,
        numStandalonePorts = numPorts,
        maxMtu = mtu,
        uplinkPortPolicy = uplink,
        linkDiscoveryProtocolConfig = linkConfig,
        lacpApiVersion = "multipleLag",
    )

    if update:
        vds = find_vds_by_name(si, vds_name)
        configSpec.configVersion = vds.config.configVersion
        return configSpec

    spec = vim.DistributedVirtualSwitch.CreateSpec()
    spec.configSpec = configSpec
    spec.productInfo = prod_info

    return spec


def _check_vds_config_spec(vds, module):

    vds_name = module.params['vds_name']
    mtu = module.params['mtu']
    discovery_protocol = module.params['discovery_protocol']
    discovery_operation = module.params['discovery_operation']
    productVersion = module.params['productVersion']
    numUplinks = module.params['numUplinks']
    numPorts = module.params['numPorts']

    current_spec = vds.config

    check_vals = [
        (vds_name == current_spec.name),
        (mtu == current_spec.maxMtu),
        (discovery_protocol == current_spec.linkDiscoveryProtocolConfig.protocol),
        (discovery_operation == current_spec.linkDiscoveryProtocolConfig.operation),
        (productVersion == current_spec.productInfo.version),
        (numUplinks == len(current_spec.uplinkPortPolicy.uplinkPortName))
    ]

    if False in check_vals:
        return False
    else:
        return True


def state_update_vds(si, module):

    vds_name = module.params['vds_name']
    vds = vds = find_vds_by_name(si, vds_name)

    config_spec = _create_vds_spec(si, True, module)

    try:
        reconfig_task = vds.ReconfigureDvs_Task(config_spec)
        changed, result = wait_for_task(reconfig_task)
    except Exception as e:
        module.fail_json(msg="Failed reconfiguring vds: {}".format(e))

    module.exit_json(changed=changed, result=str(result))


def state_exit_unchanged(si, module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def state_destroy_vds(si, module):

    vds_name = module.params['vds_name']
    vds = find_vds_by_name(si, vds_name)

    if vds is None:
        module.exit_json(msg="Could not find vds: {}".format(vds_name))

    try:
        task = vds.Destroy_Task()
        changed, result = wait_for_task(task)
    except Exception as e:
        module.fail_json(msg="Failed to destroy vds: {}".format(str(e)))

    module.exit_json(changed=changed, result=result)


def state_create_vds(si, module):

    datacenter = find_datacenter_by_name(si, module.params['datacenter_name'])
    network_folder = datacenter.networkFolder

    vds_create_spec = _create_vds_spec(si, False, module)

    try:
        if not module.check_mode:

            task = network_folder.CreateDVS_Task(vds_create_spec)
            changed, vds_created = wait_for_task(task)

            module.exit_json(changed=changed, result=vds_created.name)

    except Exception, e:
        module.fail_json(msg=str(e))


def check_vds_state(si, module):

    vds_name = module.params['vds_name']

    try:
        vds = find_vds_by_name(si, vds_name)

        if vds is None:
            return 'absent'
        elif not _check_vds_config_spec(vds, module):
            return 'update'
        else:
            return 'present'

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            datacenter_name=dict(type='str', required=True),
            vds_name=dict(type='str', required=True),
            numUplinks=dict(type='int', required=True),
            numPorts=dict(type='int', required=True),
            mtu=dict(type='int', required=True),
            discovery_protocol=dict(required=True, choices=['cdp', 'lldp'], type='str'),
            discovery_operation=dict(required=True, choices=['both', 'none', 'advertise', 'listen'], type='str'),
            productVersion=dict(type='str', required=True, choices=['6.0.0', '5.5.0', '5.1.0', '5.0.0']),
            state=dict(required=True, choices=['present', 'absent'], type='str')
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vds_states = {
        'absent': {
            'present': state_destroy_vds,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'update': state_update_vds,
            'absent': state_create_vds,
        }
    }

    si = connect_to_api(module)

    datacenter = find_datacenter_by_name(si, module.params['datacenter_name'])

    if datacenter is None:
        module.fail_json(msg="Could not find datacenter: {}".format(module.params['datacenter_name']))

    desired_state = module.params['state']
    current_state = check_vds_state(si, module)

    vds_states[desired_state][current_state](si, module)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
