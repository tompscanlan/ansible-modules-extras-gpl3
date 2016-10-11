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
module: vcenter_add_lad_vds
short_description: add a new link aggregation group to a virtual distributed switch
description:
    - add a new link aggregation group to a virtual distributed switch
options:
    vds_name:
        description:
            - name of the vds to add the lag to
        type: str
    lag_name:
        description:
            - name of the lag group
        type: str
    num_ports:
        description:
            - number of ports
        type: int
    lag_mode:
        description:
            - mode of the lag
        choices: ['active', 'passive']
        type: str
    lb_mode:
        description:
            - load balanceing mode for the lag
        choices: see argument_spec below for choices
        type: str
    state:
        description:
            - If should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: create lags
  vcenter_add_lad_vds:
    hostname: '172.16.0.100'
    username: 'administrator@corp.local'
    password: 'VMware1!'
    validate_certs: False
    vds_name: 'vds001'
    lag_name: 'lag1'
    num_ports: 2
    lag_mode: 'active'
    lb_mode: 'srcTcpUdpPort'
    state: 'present'
'''


try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vc = {}


def state_destroy_lag(module):
    module.exit_json(msg="DESTROY")


def state_exit_unchanged(module):
    module.exit_json(msg="EXIT UNCHANGED")


def state_update_lag(module):

    vds = vc['vds']
    spec = lag_spec(module, True)

    changed, result = create_lag(module, vds, spec)

    if not changed:
        module.fail_json(msg="Failed to update lag: {}".format(module.params['lag_name']))

    module.exit_json(changed=changed, result=result)


def lag_spec(module, update):

    lacp_group_config = vim.dvs.VmwareDistributedVirtualSwitch.LacpGroupConfig(
        name = module.params['lag_name'],
        mode = module.params['lag_mode'],
        uplinkNum = module.params['num_ports'],
        loadbalanceAlgorithm = module.params['lb_mode'],
    )

    if update:
        operation_mode = "edit"
        lacp_group_config.key = vc['vds_lag'].key
    else:
        operation_mode = "add"

    lacp_group_spec = vim.dvs.VmwareDistributedVirtualSwitch.LacpGroupSpec(
        lacpGroupConfig = lacp_group_config,
        operation = operation_mode,
    )

    return lacp_group_spec


def create_lag(module, vds, spec):

    changed = False
    result = None

    try:
        create_task = vds.UpdateDVSLacpGroupConfig_Task([spec])
        changed, result = wait_for_task(create_task)
    except vim.fault.DvsFault as dvs_fault:
        module.fail_json(msg="Failed to create lag with fault: {}".format(str(dvs_fault)))
    except vmodl.fault.NotSupported as not_supported:
        module.fail_json(msg="Failed to create lag. Check if multiple Link Aggregation Control Protocol is not supported on the switch".format(not_supported))
    except Exception as e:
        module.fail_json(msg="Failed to create lag: {}".format(str(e)))

    return changed, result


def state_create_lag(module):

    vds = vc['vds']
    spec = lag_spec(module, False)

    changed, result = create_lag(module, vds, spec)

    if not changed:
        module.fail_json(msg="Failed to create lag: {}".format(module.params['lag_name']))

    module.exit_json(changed=changed, result=result)


def check_lag_present(module):

    vds_lag = None
    vds = vc['vds']

    vds_lags = vds.config.lacpGroupConfig

    if not vds_lags:
        return vds_lag

    for lag in vds_lags:
        if lag.name == module.params['lag_name']:
            vds_lag = lag

    return vds_lag


def check_lag_config(module):

    lag = vc['vds_lag']

    check_vals = [
        (module.params['num_ports'] == lag.uplinkNum),
        (module.params['lag_mode'] == lag.mode),
        (module.params['lb_mode'] == lag.loadbalanceAlgorithm)
    ]

    if False in check_vals:
        return False
    else:
        return True


def check_lag_state(module):
    state = 'absent'

    si = connect_to_api(module)
    vc['si'] = si

    vds_name = module.params['vds_name']

    vds = find_dvs_by_name(si, vds_name)

    if not vds:
        module.fail_json(msg="Failed to get vds: {}".format(vds_name))

    vc['vds'] = vds

    lag = check_lag_present(module)

    if not lag:
        return state

    vc['vds_lag'] = lag

    lag_config = check_lag_config(module)

    if not lag_config:
        state = 'update'
    else:
        state = 'present'

    return state



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            vds_name=dict(type='str', required=True),
            lag_name=dict(type='str', required=True),
            num_ports=dict(type='int', required=True),
            lag_mode=dict(required=True, choices=['active', 'passive'], type='str'),
            state=dict(required=True, choices=['present', 'absent'], type='str'),
            lb_mode=dict(
                required=True, choices=[
                    'srcTcpUdpPort',
                    'srcDestIpTcpUdpPortVlan',
                    'srcIpVlan',
                    'srcDestTcpUdpPort',
                    'srcMac',
                    'destIp',
                    'destMac',
                    'vlan',
                    'srcDestIp',
                    'srcIpTcpUdpPortVlan',
                    'srcDestIpTcpUdpPort',
                    'srcDestMac',
                    'destIpTcpUdpPort',
                    'srcPortId',
                    'srcIp',
                    'srcIpTcpUdpPort',
                    'destIpTcpUdpPortVlan',
                    'destTcpUdpPort',
                    'destIpVlan',
                    'srcDestIpVlan',
                ]
            )
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    lag_states = {
        'absent': {
            'present': state_destroy_lag,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'update': state_update_lag,
            'absent': state_create_lag,
        }
    }

    desired_state = module.params['state']
    current_state = check_lag_state(module)

    lag_states[desired_state][current_state](module)

from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
