#!/usr/bin/env python

#
# INTEL CONFIDENTIAL
#
# Copyright 2013-2016 Intel Corporation All Rights Reserved.
#
# The source code contained or described herein and all documents related
# to the source code ("Material") are owned by Intel Corporation or its
# suppliers or licensors. Title to the Material remains with Intel Corporation
# or its suppliers and licensors. The Material contains trade secrets and
# proprietary and confidential information of Intel or its suppliers and
# licensors. The Material is protected by worldwide copyright and trade secret
# laws and treaty provisions. No part of the Material may be used, copied,
# reproduced, modified, published, uploaded, posted, transmitted, distributed,
# or disclosed in any way without Intel's prior express written permission.
#
# No license under any patent, copyright, trade secret or other intellectual
# property right is granted to or conferred upon you by disclosure or delivery
# of the Materials, either expressly, by implication, inducement, estoppel or
# otherwise. Any license under such intellectual property rights must be
# express and approved by Intel in writing.


import os
import sys
import socket
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")


def fatal(msg):
    sys.stderr.write("%s\n" % msg)
    sys.exit(1)

try:
    from chroma_core.models import PowerControlType, PowerControlDevice
except ImportError:
    fatal("Can't import chroma_core.models! Are you on the IML manager and is your current directory /usr/share/chroma-manager ?")
try:
    from django.db import transaction
except ImportError:
    fatal("Can't import django.db! Are you on the IML manager?")

# PowerControlType will register on database saves for IML reasons, this will cause a hang
# during the run, so disconnect it.
from django.db.models import signals
from chroma_core.models import register_power_device
signals.post_save.disconnect(register_power_device, sender = PowerControlDevice)

if __name__ == "__main__":
    try:
        ipmi = PowerControlType.objects.get(make = "IPMI", model = "1.5 (LAN)")
    except PowerControlType.DoesNotExist:
        fatal("Could not find the IPMI power type! Is the DB set up?")

    ipmi.agent = "fence_virsh"
    ipmi.default_port = 22
    ipmi.poweron_template = "%(agent)s %(options)s -a %(address)s -u %(port)s -l %(username)s -k %(home)s/.ssh/id_rsa -o on -n %(identifier)s"
    ipmi.powercycle_template = "%(agent)s %(options)s  -a %(address)s -u %(port)s -l %(username)s -k %(home)s/.ssh/id_rsa -o reboot -n %(identifier)s"
    ipmi.poweroff_template = "%(agent)s %(options)s -a %(address)s -u %(port)s -l %(username)s -k %(home)s/.ssh/id_rsa -o off -n %(identifier)s"
    ipmi.monitor_template = "%(agent)s %(options)s -a %(address)s -u %(port)s -l %(username)s -k %(home)s/.ssh/id_rsa -o monitor"
    ipmi.outlet_query_template = "%(agent)s %(options)s -a %(address)s -u %(port)s -l %(username)s -k %(home)s/.ssh/id_rsa -o status -n %(identifier)s"
    ipmi.save()

    vm_host = raw_input("Enter the IP Address of your VM Host: ")
    try:
        # there's always one...
        vm_host = socket.gethostbyaddr(vm_host)[2][0]
    except (socket.error, socket.gaierror):
        fatal("%s does not appear to be a valid address" % vm_host)

    PowerControlDevice.objects.get_or_create(device_type = ipmi, address = vm_host, port = 22)
    try:
        transaction.commit()
    except transaction.TransactionManagementError:
        pass

    print """
********* IMPORTANT: THIS IS AN UNSUPPORTED CONFIGURATION **********
************ NOT INTENDED FOR PRODUCTION DEPLOYMENTS!!! *************
********* DO NOT DISTRIBUTE THIS SCRIPT OUTSIDE OF INTEL! ***********

The IPMI power control type will now drive a KVM host to emulate power control
and STONITH, provided the following conditions are met:

    * The IML manager can ssh as root to the KVM host, WITHOUT A PASSWORD
    * Lustre servers can ssh as root to the KVM host, WITHOUT A PASSWORD
    * When adding a BMC, the hostname entered matches the vm name as shown in `virsh list` on the KVM host
"""
